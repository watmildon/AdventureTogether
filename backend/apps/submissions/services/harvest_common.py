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
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.events.models import Event
from apps.locations.geo import haversine_m
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


def quest_bbox(event: Event, quest: Quest) -> Tuple[float, float, float, float]:
    """
    (min_lon, min_lat, max_lon, max_lat) around the quest's target area, for APIs that only
    take a bounding box: the box of radius_m around a Point target, the extent of any other
    geometry, or the event perimeter's extent when the quest has no geometry. Callers still
    filter with point_in_quest_area, since a box is wider than the area itself.
    """
    geom = quest.target_geometry
    if geom is None:
        return tuple(event.bounding_polygon.extent)
    if geom.geom_type == 'Point':
        radius = quest_radius_m(quest)
        dlat = radius / 111_320.0
        dlon = radius / (111_320.0 * max(math.cos(math.radians(geom.y)), 0.01))
        return (geom.x - dlon, geom.y - dlat, geom.x + dlon, geom.y + dlat)
    return tuple(geom.extent)


def union_bbox(boxes) -> Optional[Tuple[float, float, float, float]]:
    """The smallest box covering every (min_lon, min_lat, max_lon, max_lat) box; None when empty."""
    boxes = list(boxes)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


@dataclass
class HarvestContext:
    """State for one harvest run of one event."""
    event: Event
    dry_run: bool = False
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    would_submit: List[Dict[str, Any]] = field(default_factory=list)
    # Non-error conditions worth surfacing to the host (e.g. a platform not configured).
    warnings: List[str] = field(default_factory=list)
    # Per-run caches shared by harvesters (e.g. changeset metadata keyed by (api_base, id), and
    # author-to-team matches keyed by ('team-match', platform, lowercased username)).
    cache: Dict[Any, Any] = field(default_factory=dict)

    def team_for_author(self, platform: str, author_username: str):
        """
        match_author_to_team, memoised for the run: one author usually has many contributions,
        and membership does not change meaningfully within a single run. Misses are cached too.
        """
        key = ('team-match', platform, (author_username or '').lower())
        if key not in self.cache:
            self.cache[key] = match_author_to_team(self.event, author_username, platform)
        return self.cache[key]

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
    editing). For a value-scoring quest the value is (re)read from the payload on every run, so
    an existing submission is also updated when its value changes (e.g. the scoring rule was
    added later), unless a host has set the value. Verified submissions have their quest
    progress recomputed so counted quests advance. Returns 'created', 'updated', or 'unchanged'.
    In a dry run nothing is written and the would-be submission is recorded on the context instead.
    """
    from .progress import recompute_after_change
    from .value_extraction import apply_extraction

    stats = ctx.platform(platform)
    stats['harvested'] += 1
    diff_payload = diff_payload or {}
    element_count = max(1, int(element_count or 1))

    existing = Submission.objects.filter(platform=platform, external_id=external_id).first()
    # A submission that is already credited keeps its team, so only look one up when it can be used.
    if existing is not None and existing.team_id is not None:
        team = None
    else:
        team = ctx.team_for_author(platform, author_username)

    if existing is None:
        stats['created'] += 1
        if team:
            stats['matched'] += 1
        submission = Submission(
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
        apply_extraction(quest, submission)
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
            if submission.extracted_value is not None:
                ctx.would_submit[-1]['extracted_value'] = submission.extracted_value
            return 'created'
        submission.save()
        return 'created'

    if existing.event_id != ctx.event.id:
        # Same external id already claimed by another event; leave it alone.
        return 'unchanged'

    changed_fields = []
    if element_count > existing.element_count:
        existing.element_count = element_count
        # A value a host has set survives the refreshed payload.
        stored = existing.diff_payload or {}
        kept = ({k: stored[k] for k in ('extracted_values', 'value_overridden_by') if k in stored}
                if stored.get('value_overridden_by') else {})
        existing.diff_payload = {**diff_payload, **kept}
        changed_fields += ['element_count', 'diff_payload']
    if existing.team_id is None and team is not None:
        existing.team = team
        changed_fields.append('team')
    if 'diff_payload' not in changed_fields:
        # Read the value from the stored payload topped up with keys it lacks (e.g. a Commons
        # description harvested after the submission was first stored).
        stored_payload = existing.diff_payload
        existing.diff_payload = {**diff_payload, **(stored_payload or {})}
        if apply_extraction(quest, existing):
            changed_fields += ['diff_payload', 'extracted_value']
        else:
            existing.diff_payload = stored_payload
    elif apply_extraction(quest, existing):
        changed_fields.append('extracted_value')

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
        if existing.extracted_value is not None:
            ctx.would_submit[-1]['extracted_value'] = existing.extracted_value
        return 'updated'

    existing.save(update_fields=changed_fields)
    if existing.is_verified and existing.team_id and existing.quest_id:
        recompute_after_change(existing.team, existing.quest)
    return 'updated'
