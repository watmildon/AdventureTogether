"""
Harvest orchestration (run by Django-Q2 on a schedule, by the trigger_harvest API action, and
by `manage.py harvest_event`).

Each criteria type present among an event's active quests is dispatched to its harvester, so an
event without GitHub quests never calls GitHub. A failing platform is counted and logged (by
exception class only, never with URLs) and does not stop the others.
"""

import logging
from collections import OrderedDict
from datetime import timedelta
from typing import Any, Callable, Dict, List

from django.utils import timezone

from apps.events.models import Event
from apps.quests.models import Quest
from .github_harvester import harvest_github
from .harvest_common import STAT_KEYS, HarvestContext, describe_exception
from .osm_notes_harvester import harvest_osm_notes
from .overpass_harvester import harvest_ohm_features, harvest_osm_tags
from .wikidata_harvester import harvest_wikidata_entries, harvest_wikidata_statements
from .wikimedia_harvester import harvest_commons

logger = logging.getLogger('apps.submissions.harvest')

# criteria_type -> (stats platform key, harvester). Types not listed (location_checkin,
# street_imagery) are not harvested from external APIs here.
HARVESTERS: 'OrderedDict[str, tuple]' = OrderedDict([
    ('osm_tags', ('osm', harvest_osm_tags)),
    ('ohm_feature', ('ohm', harvest_ohm_features)),
    ('osm_notes', ('osm_notes', harvest_osm_notes)),
    ('wikimedia_commons', ('commons', harvest_commons)),
    ('wikidata_entry', ('wikidata', harvest_wikidata_entries)),
    ('wikidata_statement', ('wikidata', harvest_wikidata_statements)),
    ('oss_contribution', ('github', harvest_github)),
])

# Scheduled harvests run for events whose window, padded by this much, contains now.
ACTIVE_WINDOW_PADDING = timedelta(days=1)


def _empty_stats(event_id: int, dry_run: bool) -> Dict[str, Any]:
    return {
        'event': event_id,
        'dry_run': dry_run,
        'summary': {k: 0 for k in STAT_KEYS},
        'warnings': [],
    }


def harvest_event_submissions(event_id: int, dry_run: bool = False) -> Dict[str, Any]:
    """
    Harvests every platform the event's active quests need.

    Returns {"event": id, "dry_run": bool, "<platform>": {harvested, created, updated, matched,
    errors}, ..., "summary": {same keys, totalled}, "warnings": [...]}; with dry_run also
    "would_submit": [{platform, external_id, author, element_count, quest, team, action}].
    """
    result = _empty_stats(event_id, dry_run)
    try:
        event = Event.objects.get(id=event_id, is_active=True)
    except Event.DoesNotExist:
        result['warnings'].append('event not found or inactive')
        result['found'] = False
        return result
    result['found'] = True

    quests_by_type: Dict[str, List[Quest]] = {}
    for quest in Quest.objects.filter(event=event, is_active=True).order_by('id'):
        quests_by_type.setdefault(quest.criteria_type, []).append(quest)

    ctx = HarvestContext(event=event, dry_run=dry_run)
    for criteria_type, (platform, harvester) in HARVESTERS.items():
        quests = quests_by_type.get(criteria_type)
        if not quests:
            continue
        _run_harvester(ctx, platform, criteria_type, harvester, quests)

    for platform, counts in ctx.stats.items():
        result[platform] = counts
        for key in STAT_KEYS:
            result['summary'][key] += counts[key]
    result['warnings'].extend(ctx.warnings)
    if dry_run:
        result['would_submit'] = ctx.would_submit
    return result


def _run_harvester(ctx: HarvestContext, platform: str, criteria_type: str,
                   harvester: Callable, quests: List[Quest]) -> None:
    try:
        harvester(ctx, quests)
    except Exception as exc:  # one platform failing must not stop the others
        ctx.error(platform, f'{criteria_type} harvester failed: {describe_exception(exc)}')


def events_due_for_harvest(now=None):
    now = now or timezone.now()
    return Event.objects.filter(
        is_active=True,
        start_time__lte=now + ACTIVE_WINDOW_PADDING,
        end_time__gte=now - ACTIVE_WINDOW_PADDING,
    )


def harvest_all_active_events() -> Dict[int, Dict[str, Any]]:
    """
    Scheduled task entrypoint: harvests active events whose window (start - 1 day,
    end + 1 day) contains now.
    """
    results = {}
    for event in events_due_for_harvest():
        try:
            results[event.id] = harvest_event_submissions(event.id)
        except Exception as exc:
            logger.warning('Harvest of event %s failed: %s', event.id, describe_exception(exc))
            results[event.id] = {'error': describe_exception(exc)}
    return results
