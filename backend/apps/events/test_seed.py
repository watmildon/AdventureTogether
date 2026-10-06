"""
Tests for the seed_event management command and the FOSS4G NA 2026 fixture.
"""

import copy
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.quests.models import Quest
from apps.teams.models import Team
from .models import Event

FIXTURES_DIR = Path(settings.BASE_DIR) / 'fixtures'
EVENT_FIXTURE = FIXTURES_DIR / 'foss4gna_2026.json'
SCHEDULE_FIXTURE = FIXTURES_DIR / 'foss4gna_2026_schedule.json'


def load_fixture():
    with EVENT_FIXTURE.open(encoding='utf-8') as fh:
        return json.load(fh)


class SeedEventCommandTests(TestCase):

    def setUp(self):
        self.fixture = load_fixture()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def write_seed(self, data, name='seed.json') -> str:
        path = Path(self._tmpdir.name) / name
        path.write_text(json.dumps(data), encoding='utf-8')
        return str(path)

    def seed(self, path=EVENT_FIXTURE, *extra, schedule=True) -> str:
        out = StringIO()
        args = [str(path)]
        if schedule:
            args += ['--schedule-json', str(SCHEDULE_FIXTURE)]
        call_command('seed_event', *args, *extra, stdout=out, stderr=StringIO())
        return out.getvalue()

    def counts(self):
        return Event.objects.count(), Quest.objects.count(), Team.objects.count()

    def test_seeds_event_quests_and_team_from_real_fixture(self):
        output = self.seed()

        event = Event.objects.get(slug='foss4gna-2026')
        self.assertEqual(event.title, 'FOSS4G NA 2026 Open Data Hunt')
        self.assertEqual(event.hashtag, 'FOSS4GNA2026')
        self.assertEqual(event.start_time.isoformat(), '2026-11-02T16:00:00+00:00')
        self.assertEqual(event.quests.count(), len(self.fixture['quests']))
        self.assertTrue(event.teams.filter(name='Organisers (demo)').exists())
        self.assertIn('created', output)
        self.assertNotIn('Warnings', output)

        # Every quest geometry sits inside the perimeter, and every code was expanded.
        for quest in event.quests.all():
            if quest.target_geometry is not None:
                self.assertTrue(event.is_within_bounds(quest.target_geometry), quest.title)
            self.assertIn('title', quest.inspired_by, quest.title)

        ohm = event.quests.get(title='Alkali Flat, then and now')
        self.assertEqual(ohm.inspired_by, {
            'code': '78PVFZ',
            'title': 'OpenHistoricalMap: across the geoverse',
            'speakers': ['Minh Nguyễn'],
            'start': '2026-11-04T11:00:00-08:00',
            'room': 'Beavis',
            'track': 'Community of Practice',
            'url': 'https://talks.osgeo.org/foss4g-na-2026/talk/78PVFZ/',
        })
        patch_quest = event.quests.get(title='Ship a patch')
        self.assertEqual(patch_quest.inspired_by['title'], 'Code is liability – contributing to GDAL in the LLM era')
        self.assertEqual(patch_quest.inspired_by['speakers'], ['Howard Butler'])
        self.assertEqual(patch_quest.inspired_by['room'], 'Bondi')

        # Social events carry an inline inspired_by without a code.
        icebreaker = event.quests.get(title='Icebreaker check-in')
        self.assertNotIn('code', icebreaker.inspired_by)
        self.assertEqual(icebreaker.inspired_by['url'], 'https://www.foss4gna.org/conference-events')
        self.assertEqual(icebreaker.window_start.isoformat(), '2026-11-03T02:00:00+00:00')
        self.assertTrue(icebreaker.is_open_at(icebreaker.window_start))

        hours = event.quests.get(title='Farm-to-fork hours')
        self.assertEqual(hours.target_count, 5)
        self.assertFalse(event.quests.get(title='Street view, open').is_active)

    def test_rerun_is_idempotent(self):
        self.seed()
        before = self.counts()
        join_code = Team.objects.get(name='Organisers (demo)').join_code

        output = self.seed()

        self.assertEqual(self.counts(), before)
        self.assertIn('unchanged', output)
        self.assertIn(f'0 created, 0 updated, {before[1]} unchanged, 0 deleted', output)
        self.assertEqual(Team.objects.get(name='Organisers (demo)').join_code, join_code)

    def test_rerun_updates_changed_quest(self):
        self.seed()
        data = copy.deepcopy(self.fixture)
        data['quests'][0]['points_reward'] = 99

        self.seed(self.write_seed(data))

        self.assertEqual(Quest.objects.get(title=data['quests'][0]['title']).points_reward, 99)
        self.assertEqual(Quest.objects.count(), len(data['quests']))

    def test_replace_quests_removes_quests_not_in_file(self):
        self.seed()
        event = Event.objects.get(slug='foss4gna-2026')
        Quest.objects.create(event=event, title='Retired quest', description='old', criteria_type='osm_tags')

        self.seed()  # without --replace-quests the extra quest survives
        self.assertTrue(event.quests.filter(title='Retired quest').exists())

        output = self.seed(EVENT_FIXTURE, '--replace-quests')
        self.assertFalse(event.quests.filter(title='Retired quest').exists())
        self.assertEqual(event.quests.count(), len(self.fixture['quests']))
        self.assertIn('1 deleted', output)

    def test_target_outside_perimeter_aborts_without_changes(self):
        data = copy.deepcopy(self.fixture)
        data['quests'][-1]['target_geometry'] = {'type': 'Point', 'coordinates': [-122.4, 37.8]}

        with self.assertRaisesMessage(CommandError, 'event bounding perimeter'):
            self.seed(self.write_seed(data))
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_failure_on_rerun_leaves_existing_data_untouched(self):
        self.seed()
        before = self.counts()
        data = copy.deepcopy(self.fixture)
        data['event']['title'] = 'Renamed'
        data['teams'].append({'name': 'Clash', 'join_code': Team.objects.get().join_code})

        with self.assertRaisesMessage(CommandError, 'already used'):
            self.seed(self.write_seed(data))
        self.assertEqual(self.counts(), before)
        self.assertEqual(Event.objects.get().title, 'FOSS4G NA 2026 Open Data Hunt')

    def test_unknown_code_warns_and_keeps_code(self):
        data = copy.deepcopy(self.fixture)
        data['quests'][0]['inspired_by'] = {'code': 'NOPE00'}

        output = self.seed(self.write_seed(data))

        self.assertIn('NOPE00', output)
        self.assertIn('Warnings (1)', output)
        self.assertEqual(Quest.objects.get(title=data['quests'][0]['title']).inspired_by, {'code': 'NOPE00'})

    def test_no_schedule_available_warns_with_titles(self):
        data = copy.deepcopy(self.fixture)
        data['event']['schedule_url'] = ''

        output = self.seed(self.write_seed(data), schedule=False)

        self.assertIn('No schedule available', output)
        self.assertIn('"Ship a patch"', output)
        self.assertEqual(Quest.objects.get(title='Ship a patch').inspired_by, {'code': 'VWRMCB'})

    def test_schedule_url_is_fetched_when_no_local_file(self):
        from apps.events.services.schedule import parse_frab_schedule

        with SCHEDULE_FIXTURE.open(encoding='utf-8') as fh:
            sessions = parse_frab_schedule(json.load(fh))
        with patch(
            'apps.events.management.commands.seed_event.fetch_schedule_sessions', return_value=sessions
        ) as fetch:
            self.seed(schedule=False)

        fetch.assert_called_once_with(self.fixture['event']['schedule_url'])
        self.assertEqual(Quest.objects.get(title='Close a Note').inspired_by['code'], 'LRZVUR')

    def test_invalid_criteria_type_rejected(self):
        data = copy.deepcopy(self.fixture)
        data['quests'][0]['criteria_type'] = 'telepathy'

        with self.assertRaisesMessage(CommandError, 'unknown criteria_type'):
            self.seed(self.write_seed(data))
        self.assertEqual(self.counts(), (0, 0, 0))
