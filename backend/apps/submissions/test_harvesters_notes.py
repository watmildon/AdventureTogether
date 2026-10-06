"""
Tests for the OSM Notes harvester (osm_notes quests). No network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase, override_settings

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.teams.models import Team, TeamMembership


def note_feature(note_id, lon, lat, status, comments, closed_at=None):
    props = {
        'id': note_id,
        'url': f'https://api.openstreetmap.org/api/0.6/notes/{note_id}.json',
        'date_created': comments[0]['date'],
        'status': status,
        'comments': comments,
    }
    if closed_at:
        props['closed_at'] = closed_at
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': props}


NOTES = {'type': 'FeatureCollection', 'features': [
    # Closed in window by a participant, hashtag in closing comment -> qualifies.
    note_feature(5533609, -121.4904, 38.5801, 'closed', [
        {'date': '2026-10-22 17:40:02 UTC', 'action': 'opened', 'text': 'Camera faces east now'},
        {'date': '2026-11-03 20:07:15 UTC', 'uid': 1, 'user': 'notefixer', 'action': 'closed',
         'text': 'Checked on site #FOSS4GNA2026'},
    ], closed_at='2026-11-03 20:07:15 UTC'),
    # Hashtag only in the opening comment, closed anonymously by someone else -> author falls back.
    note_feature(5533610, -121.4950, 38.5750, 'closed', [
        {'date': '2026-11-03 10:00:00 UTC', 'uid': 2, 'user': 'reporter', 'action': 'opened',
         'text': 'Bench missing #FOSS4GNA2026'},
        {'date': '2026-11-03 21:00:00 UTC', 'action': 'closed', 'text': 'done'},
    ], closed_at='2026-11-03 21:00:00 UTC'),
    # Still open -> ignored.
    note_feature(5533611, -121.4904, 38.5801, 'open', [
        {'date': '2026-11-03 10:00:00 UTC', 'uid': 3, 'user': 'x', 'action': 'opened', 'text': '#FOSS4GNA2026'},
    ]),
    # Closed before the event -> ignored.
    note_feature(5533612, -121.4904, 38.5801, 'closed', [
        {'date': '2026-09-17 16:18:03 UTC', 'uid': 4, 'user': 'y', 'action': 'opened', 'text': 'x'},
        {'date': '2026-09-17 21:00:34 UTC', 'uid': 4, 'user': 'y', 'action': 'closed', 'text': '#FOSS4GNA2026'},
    ], closed_at='2026-09-17 21:00:34 UTC'),
    # Closed in window but no hashtag -> ignored.
    note_feature(5533613, -121.4904, 38.5801, 'closed', [
        {'date': '2026-11-03 10:00:00 UTC', 'uid': 5, 'user': 'z', 'action': 'opened', 'text': 'x'},
        {'date': '2026-11-03 11:00:00 UTC', 'uid': 5, 'user': 'z', 'action': 'closed', 'text': 'fixed'},
    ], closed_at='2026-11-03 11:00:00 UTC'),
]}


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


@override_settings(OSM_API_BASE='https://osm.invalid/api/0.6')
class OsmNotesHarvesterTests(TestCase):

    def setUp(self):
        self.event = Event.objects.create(
            title='Hunt', hashtag='FOSS4GNA2026',
            bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
            start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        self.team = Team.objects.create(event=self.event, name='Note Takers')
        TeamMembership.objects.create(team=self.team, user_identifier='d1', osm_username='notefixer')
        self.anywhere = Quest.objects.create(event=self.event, title='Close a Note', description='x',
                                             criteria_type='osm_notes', validation_rules={})

    def harvest(self):
        with patch('requests.get', return_value=ok(NOTES)) as get:
            stats = harvest_event_submissions(self.event.id)
        return stats, get

    def test_request_shape(self):
        _, get = self.harvest()
        url = get.call_args.args[0]
        params = get.call_args.kwargs['params']
        self.assertEqual(url, 'https://osm.invalid/api/0.6/notes.json')
        self.assertEqual(params['bbox'], '-121.509000,38.572000,-121.481000,38.590000')
        self.assertEqual(params['closed'], -1)
        self.assertEqual(params['limit'], 100)

    def test_closed_hashtag_notes_in_window_qualify(self):
        stats, _ = self.harvest()
        self.assertEqual(stats['osm_notes']['created'], 2)
        sub = Submission.objects.get(external_id=f'5533609/q{self.anywhere.id}')
        self.assertEqual(sub.platform, 'osm_notes')
        self.assertEqual(sub.author_username, 'notefixer')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.external_url, 'https://www.openstreetmap.org/note/5533609')
        self.assertEqual(sub.element_count, 1)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 20, 7, 15, tzinfo=timezone.utc))
        self.assertEqual(sub.diff_payload['status'], 'closed')
        self.assertEqual(len(sub.diff_payload['comments']), 2)

        fallback = Submission.objects.get(external_id=f'5533610/q{self.anywhere.id}')
        self.assertEqual(fallback.author_username, 'reporter')
        self.assertIsNone(fallback.team)

    def test_note_matched_to_each_quest_whose_geometry_contains_it(self):
        near = Quest.objects.create(event=self.event, title='Near venue', description='x',
                                    criteria_type='osm_notes', validation_rules={'radius_m': 50},
                                    target_geometry=Point(-121.4905, 38.5800, srid=4326))
        far = Quest.objects.create(event=self.event, title='Elsewhere', description='x',
                                   criteria_type='osm_notes', validation_rules={},
                                   target_geometry=Polygon.from_bbox((-121.50, 38.586, -121.49, 38.589)))
        self.harvest()
        self.assertTrue(Submission.objects.filter(external_id=f'5533609/q{near.id}').exists())
        self.assertFalse(Submission.objects.filter(external_id=f'5533610/q{near.id}').exists())
        self.assertFalse(Submission.objects.filter(quest=far).exists())
        self.assertEqual(Submission.objects.filter(quest=self.anywhere).count(), 2)

    def test_http_error_counted(self):
        import requests
        resp = MagicMock()
        resp.status_code = 509
        err = requests.HTTPError('509 for url: https://osm.invalid/api/0.6/notes.json')
        err.response = resp
        resp.raise_for_status.side_effect = err
        with patch('requests.get', return_value=resp), self.assertLogs('apps.submissions.harvest') as logs:
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['osm_notes']['errors'], 1)
        self.assertNotIn('osm.invalid', '\n'.join(logs.output))
