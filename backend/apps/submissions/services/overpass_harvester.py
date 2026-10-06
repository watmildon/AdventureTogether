"""
Overpass-based harvester for map edits on OpenStreetMap (`osm_tags` quests) and
OpenHistoricalMap (`ohm_feature` quests).

For each quest an Overpass query selects the elements that currently carry the quest's
required tags, lie in the quest's target area, and were last edited since the quest window
opened. The elements are grouped by the changeset that last touched them; each changeset's
metadata is fetched from the platform's API to check the event hashtag, the author, and when it
was made. A qualifying (changeset, quest) pair becomes one Submission whose element_count is the
number of distinct matching elements.

The OSM Overpass endpoint (settings.OVERPASS_URL) is a private, secret endpoint: it is only
read from settings and never logged. When it is empty the OSM quests are skipped; there is no
fallback to a public Overpass instance.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache

from apps.events.models import Event
from apps.quests.models import Quest
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    http_post,
    parse_timestamp,
    quest_radius_m,
    quest_window_start,
    to_utc_iso,
    upsert_submission,
)
from .tag_matcher import hashtag_matches

logger = logging.getLogger('apps.submissions.harvest')

OVERPASS_QUERY_TIMEOUT = 60
OVERPASS_HTTP_TIMEOUT = 90
CHANGESET_HTTP_TIMEOUT = 30
# Closed changesets never change, so their metadata is cached across runs.
CLOSED_CHANGESET_CACHE_SECONDS = 24 * 3600

_REGEX_SPECIALS = set('.^$*+?()[]{}|\\')


@dataclass(frozen=True)
class MapPlatform:
    platform: str
    criteria_type: str
    label: str
    overpass_setting: str
    api_base_setting: str
    changeset_url: str
    default_required_tags: Dict[str, str]


OSM = MapPlatform(
    platform='osm',
    criteria_type='osm_tags',
    label='OSM',
    overpass_setting='OVERPASS_URL',
    api_base_setting='OSM_API_BASE',
    changeset_url='https://www.openstreetmap.org/changeset/{id}',
    default_required_tags={},
)

OHM = MapPlatform(
    platform='ohm',
    criteria_type='ohm_feature',
    label='OHM',
    overpass_setting='OHM_OVERPASS_URL',
    api_base_setting='OHM_API_BASE',
    changeset_url='https://www.openhistoricalmap.org/changeset/{id}',
    default_required_tags={'start_date': '*'},
)


# --- Query building -------------------------------------------------------------------------

def _ql_string(value: Any) -> str:
    """Quotes a value as an Overpass QL string literal."""
    text = str(value).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{text}"'


def _regex_escape(text: str) -> str:
    return ''.join(f'\\{c}' if c in _REGEX_SPECIALS else c for c in text)


def build_tag_filters(required_tags: Dict[str, Any]) -> str:
    """
    `{"amenity": "cafe", "opening_hours": "*"}` -> `["amenity"="cafe"]["opening_hours"]`.
    A value with `|` ("restaurant|cafe") becomes an anchored regex alternative.
    """
    parts = []
    for key, value in (required_tags or {}).items():
        if value in (None, '', '*'):
            parts.append(f'[{_ql_string(key)}]')
        elif '|' in str(value):
            options = [_regex_escape(v.strip()) for v in str(value).split('|') if v.strip()]
            parts.append(f'[{_ql_string(key)}~{_ql_string("^(" + "|".join(options) + ")$")}]')
        else:
            parts.append(f'[{_ql_string(key)}={_ql_string(value)}]')
    return ''.join(parts)


def _poly_filter(polygon) -> str:
    coords = list(polygon.exterior_ring.coords)
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return '(poly:"' + ' '.join(f'{lat:.7f} {lon:.7f}' for lon, lat in coords) + '")'


def build_area_filter(event: Event, quest: Quest) -> str:
    """
    Point target -> `(around:radius_m,lat,lon)`; Polygon target -> `(poly:"lat lon ...")`;
    no target -> the event perimeter as a poly. Other geometry types use their bounding box.
    """
    geom = quest.target_geometry
    if geom is None:
        return _poly_filter(event.bounding_polygon)
    if geom.geom_type == 'Point':
        return f'(around:{quest_radius_m(quest):g},{geom.y:.7f},{geom.x:.7f})'
    if geom.geom_type == 'Polygon':
        return _poly_filter(geom)
    return _poly_filter(geom.envelope)


def build_overpass_query(required_tags: Dict[str, Any], area_filter: str, newer_iso: str,
                         timeout: int = OVERPASS_QUERY_TIMEOUT) -> str:
    return (
        f'[out:json][timeout:{int(timeout)}];\n'
        f'nwr{build_tag_filters(required_tags)}{area_filter}(newer:{_ql_string(newer_iso)});\n'
        'out meta center;'
    )


def build_quest_query(event: Event, quest: Quest, defaults: Optional[Dict[str, str]] = None) -> str:
    rules = quest.validation_rules or {}
    required_tags = rules.get('required_tags') or dict(defaults or {})
    newer = to_utc_iso(quest_window_start(event, quest))
    return build_overpass_query(required_tags, build_area_filter(event, quest), newer)


# --- Fetching ---------------------------------------------------------------------------------

def fetch_overpass_elements(endpoint: str, query: str, what: str) -> List[Dict[str, Any]]:
    """Runs an Overpass query and returns its elements. Raises HarvestError on failure."""
    data = http_post(endpoint, what, data={'data': query}, timeout=OVERPASS_HTTP_TIMEOUT)
    remark = str(data.get('remark') or '')
    if 'error' in remark.lower():
        # Overpass reports query timeouts and memory exhaustion with HTTP 200 and a remark.
        raise HarvestError(f"{what} runtime error: {remark[:200]}")
    return data.get('elements') or []


def _extract_changeset(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # openstreetmap-website returns {"changeset": {...}}; cgimap-style responses use
    # {"elements": [{"type": "changeset", ...}]}.
    if isinstance(data.get('changeset'), dict):
        return data['changeset']
    for element in data.get('elements') or []:
        if element.get('type') == 'changeset':
            return element
    return None


def fetch_changeset_meta(ctx: HarvestContext, mp: MapPlatform, changeset_id: int) -> Dict[str, Any]:
    """Changeset metadata, fetched at most once per run (and cached across runs once closed)."""
    key = ('changeset', mp.platform, changeset_id)
    if key in ctx.cache:
        return ctx.cache[key]

    cache_key = f'harvest:changeset:{mp.platform}:{changeset_id}'
    meta = cache.get(cache_key)
    if meta is None:
        api_base = getattr(settings, mp.api_base_setting).rstrip('/')
        data = http_get(f'{api_base}/changeset/{changeset_id}.json',
                        f'{mp.label} changeset', timeout=CHANGESET_HTTP_TIMEOUT)
        cs = _extract_changeset(data)
        if not cs:
            raise HarvestError(f'{mp.label} changeset response had no changeset')
        meta = {
            'id': cs.get('id', changeset_id),
            'user': cs.get('user', ''),
            'uid': cs.get('uid'),
            'created_at': cs.get('created_at'),
            'closed_at': cs.get('closed_at'),
            'open': bool(cs.get('open', False)),
            'tags': cs.get('tags') or {},
        }
        if not meta['open'] and meta['closed_at']:
            cache.set(cache_key, meta, CLOSED_CHANGESET_CACHE_SECONDS)

    ctx.cache[key] = meta
    return meta


def _element_summary(element: Dict[str, Any]) -> Dict[str, Any]:
    center = element.get('center') or {}
    return {
        'type': element.get('type'),
        'id': element.get('id'),
        'version': element.get('version'),
        'user': element.get('user'),
        'timestamp': element.get('timestamp'),
        'lat': element.get('lat', center.get('lat')),
        'lon': element.get('lon', center.get('lon')),
        'tags': element.get('tags') or {},
    }


def group_by_changeset(elements: List[Dict[str, Any]]) -> 'OrderedDict[int, List[Dict[str, Any]]]':
    """Distinct elements (by type and id) grouped by the changeset of their current version."""
    groups: 'OrderedDict[int, OrderedDict]' = OrderedDict()
    for element in elements:
        changeset_id = element.get('changeset')
        if changeset_id is None:
            continue
        key = (element.get('type'), element.get('id'))
        groups.setdefault(changeset_id, OrderedDict())[key] = _element_summary(element)
    return OrderedDict((cs, list(elems.values())) for cs, elems in groups.items())


# --- Harvesting -------------------------------------------------------------------------------

def harvest_map_quests(ctx: HarvestContext, quests: List[Quest], mp: MapPlatform) -> None:
    event = ctx.event
    endpoint = getattr(settings, mp.overpass_setting, '') or ''
    ctx.platform(mp.platform)
    if not endpoint:
        message = f'{mp.overpass_setting} is not configured; skipped {mp.criteria_type} quests'
        logger.warning('Harvest event %s: %s', event.id, message)
        ctx.warnings.append(message)
        return

    for quest in quests:
        rules = quest.validation_rules or {}
        require_hashtag = rules.get('require_hashtag', True) is not False
        query = build_quest_query(event, quest, mp.default_required_tags)
        try:
            elements = fetch_overpass_elements(endpoint, query, f'{mp.label} Overpass')
        except HarvestError as exc:
            ctx.error(mp.platform, f'quest {quest.id}: {exc}')
            continue

        for changeset_id, matched in group_by_changeset(elements).items():
            try:
                meta = fetch_changeset_meta(ctx, mp, changeset_id)
            except HarvestError as exc:
                ctx.error(mp.platform, f'changeset {changeset_id}: {exc}')
                continue

            if require_hashtag and not hashtag_matches(meta['tags'], event.hashtag):
                continue
            created_at = parse_timestamp(meta['created_at'])
            if not counts_for_quest(event, quest, created_at):
                continue

            tags = meta['tags']
            upsert_submission(
                ctx,
                platform=mp.platform,
                quest=quest,
                external_id=f'{changeset_id}/q{quest.id}',
                external_url=mp.changeset_url.format(id=changeset_id),
                author_username=meta['user'],
                contributed_at=parse_timestamp(meta['closed_at']) or created_at,
                element_count=len(matched),
                diff_payload={
                    'changeset': {
                        'id': changeset_id,
                        'user': meta['user'],
                        'created_at': meta['created_at'],
                        'comment': tags.get('comment', ''),
                        'hashtags': tags.get('hashtags', ''),
                    },
                    'elements': matched,
                },
            )


def harvest_osm_tags(ctx: HarvestContext, quests: List[Quest]) -> None:
    harvest_map_quests(ctx, quests, OSM)


def harvest_ohm_features(ctx: HarvestContext, quests: List[Quest]) -> None:
    harvest_map_quests(ctx, quests, OHM)
