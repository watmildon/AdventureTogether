"""
Shared plumbing for the harvesters: per-run context and stats, safe HTTP calls, time-window
checks, and the create-or-update step that turns a qualifying contribution into a Submission.

Secret handling: some endpoints (OVERPASS_URL) are private. `requests` embeds the URL in
exception messages, so errors are only ever reported by exception class name and HTTP status.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from .tag_matcher import match_author_to_team

logger = logging.getLogger('apps.submissions.harvest')

DEFAULT_TIMEOUT = 30
STAT_KEYS = ('harvested', 'created', 'updated', 'matched', 'errors')


class HarvestError(Exception):
    """An external call failed. The message never contains the endpoint URL."""


def describe_exception(exc: BaseException) -> str:
    """Class name plus HTTP status when known; never str(exc), which can carry the URL."""
    label = exc.__class__.__name__
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', None)
    if status is not None:
        label = f"{label} (HTTP {status})"
    return label


def harvest_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {'User-Agent': settings.HARVEST_USER_AGENT}
    if extra:
        headers.update(extra)
    return headers


def http_request(method: str, url: str, what: str, *, timeout: int = DEFAULT_TIMEOUT,
                 expect_json: bool = True, **kwargs) -> Any:
    """
    Performs one external call and returns parsed JSON (or the response when expect_json is
    False). Any failure is re-raised as HarvestError labelled with `what` (a human name such as
    "Overpass" or "OSM notes"), so callers can count and log it without leaking the URL.
    """
    headers = harvest_headers(kwargs.pop('headers', None))
    send = requests.post if method == 'POST' else requests.get
    try:
        response = send(url, headers=headers, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response.json() if expect_json else response
    except (requests.RequestException, ValueError) as exc:
        raise HarvestError(f"{what} request failed: {describe_exception(exc)}") from None


def http_get(url: str, what: str, **kwargs) -> Any:
    return http_request('GET', url, what, **kwargs)


def http_post(url: str, what: str, **kwargs) -> Any:
    return http_request('POST', url, what, **kwargs)


def parse_timestamp(value: Any) -> Optional[datetime]:
    """
    Parses the timestamp formats the platforms use ("2026-11-03T10:00:00Z",
    "2026-11-03 10:00:00 UTC") into an aware UTC datetime.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(' UTC'):
        text = text[:-4].replace(' ', 'T') + '+00:00'
    dt = parse_datetime(text)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def quest_window_start(event: Event, quest: Quest) -> datetime:
    """Earliest moment a contribution can count for the quest."""
    if quest.window_start and quest.window_start > event.start_time:
        return quest.window_start
    return event.start_time


def counts_for_quest(event: Event, quest: Quest, dt: Optional[datetime]) -> bool:
    """A contribution counts when it falls inside the event window and the quest is open."""
    if dt is None:
        return False
    if dt < event.start_time or dt > event.end_time:
        return False
    return quest.is_open_at(dt)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def quest_radius_m(quest: Quest, default: int = 300) -> float:
    try:
        return float((quest.validation_rules or {}).get('radius_m', default))
    except (TypeError, ValueError):
        return float(default)


def point_in_quest_area(event: Event, quest: Quest, lat: float, lon: float) -> bool:
    """
    Whether a point lies in the quest's target: within radius_m of a Point target, inside a
    Polygon target, or inside the event perimeter when the quest has no geometry.
    """
    from django.contrib.gis.geos import Point

    geom = quest.target_geometry
    if geom is None:
        return event.bounding_polygon.contains(Point(lon, lat, srid=4326))
    if geom.geom_type == 'Point':
        return haversine_m(lat, lon, geom.y, geom.x) <= quest_radius_m(quest)
    return geom.contains(Point(lon, lat, srid=4326))


@dataclass
class HarvestContext:
    """State for one harvest run of one event."""
    event: Event
    dry_run: bool = False
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    would_submit: List[Dict[str, Any]] = field(default_factory=list)
    # Non-error conditions worth surfacing to the host (e.g. a platform not configured).
    warnings: List[str] = field(default_factory=list)
    # Per-run caches shared by harvesters (e.g. changeset metadata keyed by (api_base, id)).
    cache: Dict[Any, Any] = field(default_factory=dict)

    def platform(self, name: str) -> Dict[str, int]:
        if name not in self.stats:
            self.stats[name] = {k: 0 for k in STAT_KEYS}
        return self.stats[name]

    def error(self, platform: str, message: str) -> None:
        """Counts and logs an error. `message` must not contain URLs."""
        self.platform(platform)['errors'] += 1
        logger.warning("Harvest event %s, %s: %s", self.event.id, platform, message)


def upsert_submission(ctx: HarvestContext, *, platform: str, quest: Quest, external_id: str,
                      external_url: str, author_username: str, contributed_at: Optional[datetime],
                      element_count: int = 1, diff_payload: Optional[Dict[str, Any]] = None) -> str:
    """
    Creates the submission for a qualifying contribution, or refreshes an existing one.

    An existing submission is updated when more elements now match (element_count grows) or when
    its author can now be credited to a team (e.g. the member added their username after
    editing). Verified submissions have their team's quest progress recomputed so counted quests
    advance. Returns 'created', 'updated', or 'unchanged'. In a dry run nothing is written and
    the would-be submission is recorded on the context instead.
    """
    from .progress import recompute_quest_progress

    stats = ctx.platform(platform)
    stats['harvested'] += 1
    diff_payload = diff_payload or {}
    element_count = max(1, int(element_count or 1))
    team = match_author_to_team(ctx.event, author_username, platform)

    existing = Submission.objects.filter(platform=platform, external_id=external_id).first()

    if existing is None:
        stats['created'] += 1
        if team:
            stats['matched'] += 1
        if ctx.dry_run:
            ctx.would_submit.append({
                'platform': platform,
                'external_id': external_id,
                'author': author_username,
                'element_count': element_count,
                'quest': quest.id,
                'team': team.id if team else None,
                'action': 'create',
            })
            return 'created'
        Submission.objects.create(
            event=ctx.event,
            quest=quest,
            team=team,
            platform=platform,
            external_id=external_id,
            external_url=external_url,
            author_username=author_username or '',
            contributed_at=contributed_at,
            element_count=element_count,
            diff_payload=diff_payload,
        )
        return 'created'

    if existing.event_id != ctx.event.id:
        # Same external id already claimed by another event; leave it alone.
        return 'unchanged'

    changed_fields = []
    if element_count > existing.element_count:
        existing.element_count = element_count
        existing.diff_payload = diff_payload
        changed_fields += ['element_count', 'diff_payload']
    if existing.team_id is None and team is not None:
        existing.team = team
        changed_fields.append('team')

    if not changed_fields:
        return 'unchanged'

    stats['updated'] += 1
    if existing.team_id:
        stats['matched'] += 1
    if ctx.dry_run:
        ctx.would_submit.append({
            'platform': platform,
            'external_id': external_id,
            'author': author_username,
            'element_count': element_count,
            'quest': quest.id,
            'team': existing.team_id,
            'action': 'update',
        })
        return 'updated'

    existing.save(update_fields=changed_fields)
    if existing.is_verified and existing.team_id and existing.quest_id:
        recompute_quest_progress(existing.team, existing.quest)
    return 'updated'
