"""
Seeds (or re-seeds) an event, its quests and optional teams from a JSON file.

    python manage.py seed_event fixtures/foss4gna_2026.json \
        --schedule-json fixtures/foss4gna_2026_schedule.json

The command is an idempotent upsert: the event is matched by slug, quests by (event, title)
and teams by (event, name), so running it twice changes nothing the second time. Everything
runs inside one transaction, so a file that fails validation leaves the database untouched.
See documentation/seeding_events.md for the file format.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from apps.events.models import Event
from apps.events.services.schedule import (
    ScheduleFetchError,
    fetch_schedule_sessions,
    parse_frab_schedule,
)
from apps.quests.models import Quest
from apps.teams.models import Team

# Keys copied from a parsed schedule session into Quest.inspired_by.
INSPIRED_BY_KEYS = ('code', 'title', 'speakers', 'start', 'room', 'track', 'url')

VALID_CRITERIA_TYPES = {key for key, _label in Quest.CRITERIA_TYPES}


def _parse_geometry(value: Any, label: str) -> GEOSGeometry:
    """Parses a GeoJSON geometry object into a GEOSGeometry in EPSG:4326."""
    if not isinstance(value, dict) or 'type' not in value:
        raise CommandError(f'{label}: expected a GeoJSON geometry object with a "type".')
    try:
        geometry = GEOSGeometry(json.dumps(value))
    except (ValueError, TypeError, GEOSException, GDALException) as exc:
        raise CommandError(f'{label}: invalid GeoJSON geometry ({exc}).') from exc
    if geometry.srid is None:
        geometry.srid = 4326
    if not geometry.valid:
        raise CommandError(f'{label}: geometry is not valid ({geometry.valid_reason}).')
    return geometry


def _parse_datetime(value: Any, label: str, required: bool = True):
    """Parses an ISO 8601 datetime string; offsets are kept, naive values are rejected."""
    if value in (None, ''):
        if required:
            raise CommandError(f'{label} is required.')
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        raise CommandError(f'{label}: "{value}" is not an ISO 8601 datetime.')
    if parsed.tzinfo is None:
        raise CommandError(f'{label}: "{value}" needs a UTC offset, e.g. 2026-11-02T08:00:00-08:00.')
    return parsed


def _is_code_only(inspired_by: Dict[str, Any]) -> bool:
    """True when inspired_by is just {"code": "..."} and should be expanded from the schedule."""
    return set(inspired_by.keys()) == {'code'} and bool(inspired_by.get('code'))


def _apply(instance, values: Dict[str, Any]) -> bool:
    """Sets attributes on a model instance and reports whether anything actually changed."""
    changed = False
    for field, value in values.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed = True
    return changed


class Command(BaseCommand):
    help = (
        'Create or update an event, its quests and optional teams from a JSON seed file. '
        'Quests whose inspired_by is just {"code": "..."} are expanded from the conference schedule.'
    )

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the event seed JSON file.')
        parser.add_argument(
            '--schedule-json',
            dest='schedule_json',
            help=(
                'Local pretalx/frab schedule export used to expand inspired_by codes. '
                "Without it, the event's schedule_url is fetched over the network."
            ),
        )
        parser.add_argument(
            '--replace-quests',
            action='store_true',
            dest='replace_quests',
            help="Delete the event's quests whose titles are not in the seed file.",
        )

    # ------------------------------------------------------------------ entry point

    def handle(self, *args, **options):
        self.warnings: List[str] = []
        data = self._load_json(options['path'], 'Seed file')
        if not isinstance(data, dict) or not isinstance(data.get('event'), dict):
            raise CommandError('Seed file must be a JSON object with an "event" object.')

        event_values = self._clean_event(data['event'])
        quests = data.get('quests') or []
        teams = data.get('teams') or []
        if not isinstance(quests, list) or not isinstance(teams, list):
            raise CommandError('"quests" and "teams" must be JSON arrays when present.')

        # An unsaved Event carries the polygon so quest geometries can be checked with the
        # same Event.is_within_bounds rule the QuestSerializer uses, before anything is written.
        bounds = Event(bounding_polygon=event_values['bounding_polygon'])
        quest_values = [self._clean_quest(q, i, bounds) for i, q in enumerate(quests)]
        self._check_unique([q['title'] for q in quest_values], 'quest title')
        team_values = [self._clean_team(t, i) for i, t in enumerate(teams)]
        self._check_unique([t['name'] for t in team_values], 'team name')

        self._expand_inspired_by(quest_values, event_values, options.get('schedule_json'))

        with transaction.atomic():
            summary = self._write(event_values, quest_values, team_values, options['replace_quests'])

        self._print_summary(summary)

    # ------------------------------------------------------------------ validation

    def _load_json(self, path: str, label: str):
        file_path = Path(path)
        if not file_path.is_file():
            raise CommandError(f'{label} not found: {path}')
        try:
            with file_path.open(encoding='utf-8') as fh:
                return json.load(fh)
        except (OSError, ValueError) as exc:
            raise CommandError(f'{label} {path} is not valid JSON: {exc}') from exc

    def _clean_event(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        title = (raw.get('title') or '').strip()
        if not title:
            raise CommandError('event.title is required.')
        hashtag = (raw.get('hashtag') or '').lstrip('#').strip()
        if not hashtag:
            raise CommandError('event.hashtag is required.')
        slug = (raw.get('slug') or '').strip() or slugify(title)

        polygon = _parse_geometry(raw.get('bounding_polygon'), 'event.bounding_polygon')
        if polygon.geom_type != 'Polygon':
            raise CommandError(f'event.bounding_polygon must be a Polygon, got {polygon.geom_type}.')

        start_time = _parse_datetime(raw.get('start_time'), 'event.start_time')
        end_time = _parse_datetime(raw.get('end_time'), 'event.end_time')
        if end_time <= start_time:
            raise CommandError('event.end_time must be after event.start_time.')

        return {
            'title': title,
            'slug': slug,
            'description': raw.get('description') or '',
            'hashtag': hashtag,
            'bounding_polygon': polygon,
            'start_time': start_time,
            'end_time': end_time,
            'is_active': bool(raw.get('is_active', True)),
            'schedule_url': raw.get('schedule_url') or '',
        }

    def _clean_quest(self, raw: Any, index: int, bounds: Event) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raise CommandError(f'quests[{index}] must be a JSON object.')
        title = (raw.get('title') or '').strip()
        label = f'quests[{index}] "{title}"' if title else f'quests[{index}]'
        if not title:
            raise CommandError(f'{label}: title is required.')

        criteria_type = raw.get('criteria_type', 'osm_tags')
        if criteria_type not in VALID_CRITERIA_TYPES:
            raise CommandError(
                f'{label}: unknown criteria_type "{criteria_type}". '
                f'Expected one of: {", ".join(sorted(VALID_CRITERIA_TYPES))}.'
            )

        validation_rules = raw.get('validation_rules') or {}
        if not isinstance(validation_rules, dict):
            raise CommandError(f'{label}: validation_rules must be a JSON object.')

        target_geometry = None
        if raw.get('target_geometry') is not None:
            target_geometry = _parse_geometry(raw['target_geometry'], f'{label} target_geometry')
            if not bounds.is_within_bounds(target_geometry):
                raise CommandError(
                    f'{label}: target_geometry must reside within or intersect the event bounding perimeter.'
                )

        window_start = _parse_datetime(raw.get('window_start'), f'{label} window_start', required=False)
        window_end = _parse_datetime(raw.get('window_end'), f'{label} window_end', required=False)
        if window_start and window_end and window_start > window_end:
            raise CommandError(f'{label}: window_end must be on or after window_start.')

        points = raw.get('points_reward', 10)
        if isinstance(points, bool) or not isinstance(points, int):
            raise CommandError(f'{label}: points_reward must be an integer.')

        inspired_by = raw.get('inspired_by') or {}
        if not isinstance(inspired_by, dict):
            raise CommandError(f'{label}: inspired_by must be a JSON object or null.')

        return {
            'title': title,
            'description': raw.get('description') or '',
            'criteria_type': criteria_type,
            'validation_rules': validation_rules,
            'target_geometry': target_geometry,
            'points_reward': points,
            'is_active': bool(raw.get('is_active', True)),
            'window_start': window_start,
            'window_end': window_end,
            'inspired_by': dict(inspired_by),
        }

    def _clean_team(self, raw: Any, index: int) -> Dict[str, Any]:
        if not isinstance(raw, dict) or not (raw.get('name') or '').strip():
            raise CommandError(f'teams[{index}] must be an object with a non-empty "name".')
        team = {'name': raw['name'].strip()}
        if raw.get('join_code'):
            team['join_code'] = str(raw['join_code']).strip().upper()
        return team

    @staticmethod
    def _check_unique(values: List[str], label: str):
        seen = set()
        for value in values:
            if value in seen:
                raise CommandError(f'Duplicate {label} in seed file: "{value}".')
            seen.add(value)

    # ------------------------------------------------------------------ inspired_by

    def _load_sessions(self, schedule_json: Optional[str], schedule_url: str) -> Optional[List[Dict[str, Any]]]:
        """Returns parsed schedule sessions, or None (with a warning) when no schedule is available."""
        try:
            if schedule_json:
                return parse_frab_schedule(self._load_json(schedule_json, 'Schedule file'))
            if schedule_url:
                self.stdout.write(f'Fetching schedule from {schedule_url} ...')
                return fetch_schedule_sessions(schedule_url)
        except ScheduleFetchError as exc:
            self.warnings.append(f'Could not load the schedule: {exc}')
            return None
        return None

    def _expand_inspired_by(self, quest_values, event_values, schedule_json: Optional[str]):
        """Replaces code-only inspired_by dicts with the full session from the schedule export."""
        pending = [q for q in quest_values if _is_code_only(q['inspired_by'])]
        if not pending:
            return

        schedule_url = event_values['schedule_url']
        if not schedule_url:
            existing = Event.objects.filter(slug=event_values['slug']).only('schedule_url').first()
            schedule_url = existing.schedule_url if existing else ''

        sessions = self._load_sessions(schedule_json, schedule_url)
        if sessions is None:
            titles = ', '.join(f'"{q["title"]}"' for q in pending)
            self.warnings.append(
                'No schedule available (pass --schedule-json or set event.schedule_url); '
                f'inspired_by left as code only for: {titles}'
            )
            return

        by_code = {s['code']: s for s in sessions if s.get('code')}
        for quest in pending:
            code = quest['inspired_by']['code']
            session = by_code.get(code)
            if session is None:
                self.warnings.append(
                    f'Session code "{code}" (quest "{quest["title"]}") is not in the schedule; '
                    'inspired_by left as code only.'
                )
                continue
            quest['inspired_by'] = {key: session.get(key) for key in INSPIRED_BY_KEYS}

    # ------------------------------------------------------------------ writes

    def _write(self, event_values, quest_values, team_values, replace_quests: bool) -> Dict[str, Any]:
        summary = {
            'quests': {'created': [], 'updated': [], 'unchanged': [], 'deleted': []},
            'teams': {'created': [], 'updated': [], 'unchanged': []},
        }

        event = Event.objects.filter(slug=event_values['slug']).first()
        if event is None:
            event = Event.objects.create(**event_values)
            summary['event'] = 'created'
        elif _apply(event, event_values):
            event.save()
            summary['event'] = 'updated'
        else:
            summary['event'] = 'unchanged'
        summary['event_obj'] = event

        existing_quests = {q.title: q for q in event.quests.all()}
        for values in quest_values:
            quest = existing_quests.get(values['title'])
            if quest is None:
                Quest.objects.create(event=event, **values)
                summary['quests']['created'].append(values['title'])
            elif _apply(quest, values):
                quest.save()
                summary['quests']['updated'].append(values['title'])
            else:
                summary['quests']['unchanged'].append(values['title'])

        if replace_quests:
            keep = {q['title'] for q in quest_values}
            for title, quest in existing_quests.items():
                if title not in keep:
                    # Submissions keep their row (quest FK is SET_NULL); QuestProgress rows cascade, and
                    # the pre_delete receiver in apps.submissions.signals revokes awarded points.
                    quest.delete()
                    summary['quests']['deleted'].append(title)

        existing_teams = {t.name: t for t in event.teams.all()}
        for values in team_values:
            join_code = values.get('join_code')
            team = existing_teams.get(values['name'])
            if join_code and Team.objects.filter(join_code=join_code).exclude(pk=getattr(team, 'pk', None)).exists():
                raise CommandError(f'Team "{values["name"]}": join_code {join_code} is already used by another team.')
            if team is None:
                team = Team.objects.create(event=event, **values)
                summary['teams']['created'].append(team)
            elif join_code and _apply(team, {'join_code': join_code}):
                team.save()
                summary['teams']['updated'].append(team)
            else:
                summary['teams']['unchanged'].append(team)

        return summary

    # ------------------------------------------------------------------ output

    def _print_summary(self, summary: Dict[str, Any]):
        event = summary['event_obj']
        style = self.style.SUCCESS if summary['event'] != 'unchanged' else self.style.NOTICE
        self.stdout.write(style(f'Event "{event.title}" ({event.slug}): {summary["event"]}'))

        quests = summary['quests']
        self.stdout.write(
            f'Quests: {len(quests["created"])} created, {len(quests["updated"])} updated, '
            f'{len(quests["unchanged"])} unchanged, {len(quests["deleted"])} deleted'
        )
        for title in quests['created']:
            self.stdout.write(self.style.SUCCESS(f'  + {title}'))
        for title in quests['updated']:
            self.stdout.write(self.style.SUCCESS(f'  ~ {title}'))
        for title in quests['deleted']:
            self.stdout.write(self.style.WARNING(f'  - {title}'))

        teams = summary['teams']
        if any(teams.values()):
            self.stdout.write(
                f'Teams: {len(teams["created"])} created, {len(teams["updated"])} updated, '
                f'{len(teams["unchanged"])} unchanged'
            )
            for bucket in ('created', 'updated', 'unchanged'):
                for team in teams[bucket]:
                    self.stdout.write(f'  {team.name}: join code {team.join_code} ({bucket})')

        if self.warnings:
            self.stdout.write(self.style.WARNING(f'Warnings ({len(self.warnings)}):'))
            for warning in self.warnings:
                self.stdout.write(self.style.WARNING(f'  ! {warning}'))
