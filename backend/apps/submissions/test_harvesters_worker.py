"""
Tests for harvest orchestration, the trigger_harvest API action, and the management commands.
No network.
"""

import json
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Polygon
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone
from django_q.models import Schedule
from rest_framework.test import APIClient

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services import harvest_worker
from apps.submissions.services.harvest_worker import (
    harvest_all_active_events,
    harvest_event_submissions,
)

STAT_KEYS = {'harvested', 'created', 'updated', 'matched', 'errors'}


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def make_event(start=None, end=None, **kwargs):
    start = start or datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)
    return Event.objects.create(
        title=kwargs.pop('title', 'Hunt'), hashtag='FOSS4GNA2026',
        bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
        start_time=start, end_time=end or start + timedelta(days=2), **kwargs,
    )


NOTES = {'type': 'FeatureCollection', 'features': [{
    'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-121.49, 38.58]},
    'properties': {'id': 1, 'status': 'closed', 'closed_at': '2026-11-03 10:00:00 UTC', 'comments': [
        {'date': '2026-11-03 10:00:00 UTC', 'user': 'u', 'action': 'closed', 'text': '#FOSS4GNA2026'}]},
}]}


@override_settings(OVERPASS_URL='https://overpass.private.invalid/api/interpreter')
class HarvestDispatchTests(TestCase):

    def setUp(self):
        self.event = make_event()

    def test_only_present_criteria_types_are_harvested(self):
        Quest.objects.create(event=self.event, title='Note', description='x', criteria_type='osm_notes')
        Quest.objects.create(event=self.event, title='Checkin', description='x', criteria_type='location_checkin')
        Quest.objects.create(event=self.event, title='Inactive PR', description='x',
                             criteria_type='oss_contribution', is_active=False)
        with patch('requests.get', return_value=ok(NOTES)) as get, patch('requests.post') as post:
            stats = harvest_event_submissions(self.event.id)

        post.assert_not_called()  # no osm_tags/ohm quests -> no Overpass
        self.assertEqual(get.call_count, 1)
        self.assertTrue(get.call_args.args[0].endswith('/notes.json'))
        self.assertNotIn('github', stats)
        self.assertEqual(set(stats['osm_notes']), STAT_KEYS)
        self.assertEqual(stats['summary'], {'harvested': 1, 'created': 1, 'updated': 0, 'matched': 0, 'errors': 0})
        self.assertEqual(stats['event'], self.event.id)
        self.assertFalse(stats['dry_run'])
        self.assertNotIn('would_submit', stats)

    def test_one_platform_crashing_does_not_stop_others(self):
        Quest.objects.create(event=self.event, title='Note', description='x', criteria_type='osm_notes')
        Quest.objects.create(event=self.event, title='Photo', description='x', criteria_type='wikimedia_commons')
        with patch.dict(harvest_worker.HARVESTERS,
                        {'wikimedia_commons': ('commons', MagicMock(side_effect=RuntimeError('boom')))}), \
                patch('requests.get', return_value=ok(NOTES)), \
                self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['commons']['errors'], 1)
        self.assertEqual(stats['osm_notes']['created'], 1)
        self.assertEqual(stats['summary']['errors'], 1)
        self.assertIn('RuntimeError', '\n'.join(logs.output))

    def test_dry_run_lists_would_be_submissions(self):
        quest = Quest.objects.create(event=self.event, title='Note', description='x', criteria_type='osm_notes')
        with patch('requests.get', return_value=ok(NOTES)):
            stats = harvest_event_submissions(self.event.id, dry_run=True)
        self.assertEqual(Submission.objects.count(), 0)
        self.assertTrue(stats['dry_run'])
        self.assertEqual(stats['would_submit'], [{
            'platform': 'osm_notes', 'external_id': f'1/q{quest.id}', 'author': 'u',
            'element_count': 1, 'quest': quest.id, 'team': None, 'action': 'create'}])

    def test_unknown_event(self):
        stats = harvest_event_submissions(999999)
        self.assertFalse(stats['found'])
        self.assertEqual(stats['summary']['created'], 0)


class HarvestAllActiveEventsTests(TestCase):

    def test_only_events_within_padded_window(self):
        now = dj_timezone.now()
        running = make_event(start=now - timedelta(hours=2), end=now + timedelta(hours=2), title='Running')
        starts_soon = make_event(start=now + timedelta(hours=20), end=now + timedelta(days=2), title='Soon')
        just_ended = make_event(start=now - timedelta(days=3), end=now - timedelta(hours=20), title='Ended')
        make_event(start=now + timedelta(days=3), end=now + timedelta(days=4), title='Later')
        make_event(start=now - timedelta(days=5), end=now - timedelta(days=3), title='Long gone')
        make_event(start=now - timedelta(hours=1), end=now + timedelta(hours=1), title='Off', is_active=False)

        with patch.object(harvest_worker, 'harvest_event_submissions', return_value={'ok': True}) as h:
            results = harvest_all_active_events()
        self.assertEqual(sorted(results), sorted([running.id, starts_soon.id, just_ended.id]))
        self.assertEqual(h.call_count, 3)


class TriggerHarvestApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.event = make_event()

    def test_returns_new_stats_shape(self):
        Quest.objects.create(event=self.event, title='Note', description='x', criteria_type='osm_notes')
        with patch('requests.get', return_value=ok(NOTES)):
            resp = self.client.post('/api/submissions/trigger_harvest/', {'event': self.event.id}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['stats']['osm_notes']['created'], 1)
        self.assertEqual(resp.data['stats']['summary']['created'], 1)

    def test_missing_and_unknown_event(self):
        self.assertEqual(self.client.post('/api/submissions/trigger_harvest/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/submissions/trigger_harvest/', {'event': 'abc'},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/submissions/trigger_harvest/', {'event': 999999},
                                          format='json').status_code, 404)


class ManagementCommandTests(TestCase):

    def test_setup_schedules_is_idempotent(self):
        call_command('setup_schedules', stdout=StringIO())
        call_command('setup_schedules', stdout=StringIO())
        self.assertEqual(Schedule.objects.count(), 2)
        harvest = Schedule.objects.get(name='harvest_all_active_events')
        self.assertEqual(harvest.func, 'apps.submissions.services.harvest_worker.harvest_all_active_events')
        self.assertEqual((harvest.schedule_type, harvest.minutes, harvest.repeats), (Schedule.MINUTES, 5, -1))
        cleanup = Schedule.objects.get(name='cleanup_expired_pings')
        self.assertEqual(cleanup.func, 'apps.locations.views.cleanup_expired_pings')
        self.assertEqual((cleanup.schedule_type, cleanup.minutes, cleanup.repeats), (Schedule.MINUTES, 10, -1))

    def test_harvest_event_dry_run_prints_json_and_writes_nothing(self):
        event = make_event()
        Quest.objects.create(event=event, title='Note', description='x', criteria_type='osm_notes')
        out = StringIO()
        with patch('requests.get', return_value=ok(NOTES)):
            call_command('harvest_event', str(event.id), '--dry-run', stdout=out)
        stats = json.loads(out.getvalue())
        self.assertTrue(stats['dry_run'])
        self.assertEqual(len(stats['would_submit']), 1)
        self.assertEqual(Submission.objects.count(), 0)

    def test_harvest_event_unknown_event_errors(self):
        with self.assertRaises(CommandError):
            call_command('harvest_event', '999999', stdout=StringIO())
