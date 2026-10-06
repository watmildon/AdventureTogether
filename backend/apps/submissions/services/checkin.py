"""
GPS check-in quests (criteria_type 'location_checkin').

Check-ins are verified server-side from foreground LocationPings; there is no external API.
Each participant gets one Submission per check-in quest (platform 'checkin'). The first ping
inside the quest's radius creates it as evidence; later in-range pings extend it. Once the
participant has stayed in range for validation_rules['min_minutes'] (0 = immediately), the
submission is auto-verified through services.progress, which settles the team's QuestProgress
and score. Auto-verification happens at most once per submission, so a host revocation sticks.

validation_rules: {"radius_m": 50, "min_minutes": 0}. target_geometry is a Point (used
directly) or a Polygon (its centroid is the target, and any ping inside the polygon counts as
in range). Quests without a target geometry are ignored.

LocationPing keeps one row per (event, participant) that is overwritten on every ping, so all
dwell state lives in the submission's diff_payload rather than in ping history.
"""

import hashlib
import logging
from datetime import datetime, timedelta

from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone

from apps.locations.geo import haversine_m
from apps.quests.models import Quest
from apps.teams.models import TeamMembership
from apps.submissions.models import Submission
from apps.submissions.services.progress import mark_verified, recompute_quest_progress

logger = logging.getLogger(__name__)

PLATFORM = 'checkin'
SYSTEM_VERIFIER = 'system:checkin'
DEFAULT_RADIUS_M = 50.0
DEFAULT_MIN_MINUTES = 0.0
# If an unverified participant has not pinged in range for this long, their dwell clock restarts:
# being near the plaque at 9:00 and again at 15:00 is not "five minutes at the plaque".
DWELL_GAP_MINUTES = 10


def checkin_rules(quest: Quest) -> tuple[float, float]:
    """Returns (radius_m, min_minutes) from validation_rules, falling back to defaults on bad input."""
    rules = quest.validation_rules if isinstance(quest.validation_rules, dict) else {}
    try:
        radius = float(rules.get('radius_m', DEFAULT_RADIUS_M))
        if radius <= 0:
            radius = DEFAULT_RADIUS_M
    except (TypeError, ValueError):
        radius = DEFAULT_RADIUS_M
    try:
        min_minutes = max(0.0, float(rules.get('min_minutes', DEFAULT_MIN_MINUTES)))
    except (TypeError, ValueError):
        min_minutes = DEFAULT_MIN_MINUTES
    return radius, min_minutes


def distance_to_target(quest: Quest, point: Point) -> float | None:
    """
    Metres from `point` to the quest target: the Point itself, or the centroid of any other
    geometry. A point inside a polygon target is 0 m away. None when the quest has no target.
    """
    geom = quest.target_geometry
    if geom is None or geom.empty:
        return None
    if geom.srid and geom.srid != 4326:
        geom = geom.transform(4326, clone=True)
    if geom.geom_type == 'Point':
        center = geom
    else:
        if 'Polygon' in geom.geom_type and geom.contains(point):
            return 0.0
        center = geom.centroid
    return haversine_m(point.y, point.x, center.y, center.x)


def checkin_external_id(quest_id: int, user_identifier: str) -> str:
    """Stable external_id for one participant's check-in on one quest (fits the 255-char column)."""
    external_id = f"q{quest_id}/{user_identifier}"
    if len(external_id) > 255:
        digest = hashlib.sha256(user_identifier.encode('utf-8')).hexdigest()
        external_id = f"q{quest_id}/sha256:{digest}"
    return external_id


def checkin_status(submission: Submission) -> str:
    """'verified', 'revoked' (auto-verified then un-verified by a host), or 'pending'."""
    if submission.is_verified:
        return 'verified'
    if (submission.diff_payload or {}).get('auto_verified_at'):
        return 'revoked'
    return 'pending'


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _resolve_team(ping):
    membership = TeamMembership.objects.filter(
        team__event_id=ping.event_id,
        user_identifier=ping.user_identifier,
    ).select_related('team').first()
    return membership.team if membership else None


def _record_in_range(quest, ping, team, now, distance, radius, min_minutes) -> Submission:
    lat, lon = ping.coordinates.y, ping.coordinates.x
    rounded_distance = round(distance, 1)

    with transaction.atomic():
        submission, created = Submission.objects.select_for_update().get_or_create(
            platform=PLATFORM,
            external_id=checkin_external_id(quest.id, ping.user_identifier),
            defaults={
                'event_id': ping.event_id,
                'quest': quest,
                'team': team,
                'author_username': ping.display_name,
                'external_url': f"https://www.openstreetmap.org/#map=19/{lat:.6f}/{lon:.6f}",
                'element_count': 1,
                'contributed_at': now,
                'diff_payload': {
                    'user_identifier': ping.user_identifier,
                    'first_seen': _iso(now),
                    'dwell_start': _iso(now),
                    'last_seen': _iso(now),
                    'ping_count': 1,
                    'distance_m': rounded_distance,
                    'radius_m': radius,
                    'min_minutes': min_minutes,
                },
            },
        )

        payload = dict(submission.diff_payload or {})
        update_fields = []
        newly_teamed = False

        if not created:
            last_seen = _parse(payload.get('last_seen'))
            awaiting_dwell = not submission.is_verified and not payload.get('auto_verified_at')
            if awaiting_dwell and (last_seen is None or now - last_seen > timedelta(minutes=DWELL_GAP_MINUTES)):
                payload['dwell_start'] = _iso(now)
            payload.setdefault('first_seen', _iso(now))
            payload['last_seen'] = _iso(now)
            payload['ping_count'] = int(payload.get('ping_count', 0)) + 1
            payload['distance_m'] = rounded_distance
            payload['radius_m'] = radius
            payload['min_minutes'] = min_minutes
            update_fields.append('diff_payload')

            # A participant who checked in before joining a team gets their team credited later.
            if submission.team_id is None and team is not None:
                submission.team = team
                update_fields.append('team')
                newly_teamed = True

        dwell_start = _parse(payload.get('dwell_start')) or _parse(payload.get('first_seen')) or now
        should_verify = (
            not submission.is_verified
            and not payload.get('auto_verified_at')
            and now - dwell_start >= timedelta(minutes=min_minutes)
        )
        if should_verify:
            payload['auto_verified_at'] = _iso(now)
            if 'diff_payload' not in update_fields:
                update_fields.append('diff_payload')

        if update_fields:
            submission.diff_payload = payload
            submission.save(update_fields=update_fields)

        if should_verify:
            mark_verified(submission, by=SYSTEM_VERIFIER)
        elif newly_teamed and submission.is_verified:
            recompute_quest_progress(submission.team, quest)

    return submission


def process_checkin_ping(ping) -> list[Submission]:
    """
    Applies one saved LocationPing to the event's open check-in quests and returns the
    participant's check-in submissions for every quest the ping is in range of.
    """
    if not ping.is_foreground or ping.coordinates is None:
        return []

    now = ping.recorded_at or timezone.now()
    quests = Quest.objects.filter(
        event_id=ping.event_id,
        criteria_type='location_checkin',
        is_active=True,
        target_geometry__isnull=False,
    )

    team = None
    team_resolved = False
    results = []
    for quest in quests:
        if not quest.is_open_at(now):
            continue
        radius, min_minutes = checkin_rules(quest)
        distance = distance_to_target(quest, ping.coordinates)
        if distance is None or distance > radius:
            continue
        if not team_resolved:
            team = _resolve_team(ping)
            team_resolved = True
        try:
            results.append(_record_in_range(quest, ping, team, now, distance, radius, min_minutes))
        except Exception:
            # One broken quest must not stop the participant's other check-ins.
            logger.exception("Check-in failed for quest %s, participant %s", quest.id, ping.user_identifier)
    return results


def ping_checkin_summary(submission: Submission) -> dict:
    """Shape used in the ping response: this ping's in-range quests."""
    return {
        'quest': submission.quest_id,
        'quest_title': submission.quest.title if submission.quest_id else None,
        'status': 'verified' if submission.is_verified else 'in_range',
        'distance_m': (submission.diff_payload or {}).get('distance_m'),
    }


def participant_checkins(event_id, user_identifier: str) -> list[Submission]:
    """A participant's check-in submissions for an event, newest quest activity first."""
    quests = Quest.objects.filter(event_id=event_id, criteria_type='location_checkin')
    external_ids = [checkin_external_id(q.id, user_identifier) for q in quests]
    if not external_ids:
        return []
    return list(
        Submission.objects.filter(platform=PLATFORM, event_id=event_id, external_id__in=external_ids)
        .select_related('quest')
        .order_by('-contributed_at')
    )
