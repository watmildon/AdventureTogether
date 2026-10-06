"""
Unit and Integration Tests for Event Lifecycle and Spatial Boundary Validation.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import requests
from django.contrib.gis.geos import Polygon, Point
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.quests.models import Quest
from apps.submissions.models import QuestProgress
from apps.teams.models import Team, TeamMembership
from .models import Event
from .services.schedule import ScheduleFetchError, fetch_schedule_sessions, schedule_url_error


class EventModelSpatialTests(TestCase):
    """
    Tests spatial bounding perimeter calculations and model behaviors.
    """

    def setUp(self):
        # Bounding box roughly around central San Francisco: (lon, lat)
        self.sf_polygon = Polygon([
            (-122.43, 37.76),
            (-122.40, 37.76),
            (-122.40, 37.79),
            (-122.43, 37.79),
            (-122.43, 37.76),
        ])
        now = datetime.now(timezone.utc)
        self.event = Event.objects.create(
            title="San Francisco Landmark Hunt",
            description="Explore and map historic landmarks in San Francisco.",
            hashtag="#SFMapHunt2026",
            bounding_polygon=self.sf_polygon,
            start_time=now,
            end_time=now + timedelta(hours=6),
            is_active=True
        )

    def test_hashtag_and_slug_normalization(self):
        """Ensures leading hash symbol is stripped and slug is automatically generated."""
        self.assertEqual(self.event.hashtag, "SFMapHunt2026")
        self.assertEqual(self.event.slug, "san-francisco-landmark-hunt")

    def test_spatial_containment_positive(self):
        """Point inside the perimeter returns True."""
        inside_point = Point(-122.415, 37.775)
        self.assertTrue(self.event.is_within_bounds(inside_point))

    def test_spatial_containment_negative(self):
        """Point outside the perimeter returns False."""
        outside_point = Point(-122.50, 37.85)  # Far outside
        self.assertFalse(self.event.is_within_bounds(outside_point))


class EventAPITests(TestCase):
    """
    Integration tests for Event REST endpoints and GeoJSON serialization.
    """

    def setUp(self):
        self.client = APIClient()
        self.sf_polygon = Polygon([
            (-122.43, 37.76),
            (-122.40, 37.76),
            (-122.40, 37.79),
            (-122.43, 37.79),
            (-122.43, 37.76),
        ])
        now = datetime.now(timezone.utc)
        self.event = Event.objects.create(
            title="Mission District Hunt",
            description="Map opening hours in the Mission.",
            hashtag="MissionHunt",
            bounding_polygon=self.sf_polygon,
            start_time=now,
            end_time=now + timedelta(hours=4),
        )

    def test_list_events(self):
        """GET /api/events/ returns list of events."""
        url = reverse('events:event-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "Mission District Hunt")

    def test_event_geojson_endpoint(self):
        """GET /api/events/<id>/geojson/ returns valid GeoJSON Feature."""
        url = reverse('events:event-geojson', kwargs={'pk': self.event.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('type'), 'Feature')
        self.assertEqual(response.data['geometry']['type'], 'Polygon')
        self.assertEqual(response.data['properties']['hashtag'], 'MissionHunt')


class EventCreateAPITests(TestCase):
    """
    Integration tests for POST /api/events/ slug handling.
    """

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('events:event-list')
        now = datetime.now(timezone.utc)
        # Minimal valid payload; note that no slug is supplied
        self.payload = {
            'title': 'Golden Gate Park Hunt',
            'description': 'Map benches and drinking water in the park.',
            'hashtag': 'GGParkHunt',
            'bounding_polygon': {
                'type': 'Polygon',
                'coordinates': [[
                    [-122.51, 37.76], [-122.45, 37.76],
                    [-122.45, 37.78], [-122.51, 37.78],
                    [-122.51, 37.76],
                ]],
            },
            'start_time': now.isoformat(),
            'end_time': (now + timedelta(hours=3)).isoformat(),
        }

    def test_create_without_slug_generates_one(self):
        """Omitting slug is accepted and the slug is derived from the title."""
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['slug'], 'golden-gate-park-hunt')

    def test_create_with_blank_slug_generates_one(self):
        """An explicitly blank slug is treated the same as omitting it."""
        response = self.client.post(self.url, {**self.payload, 'slug': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['slug'], 'golden-gate-park-hunt')

    def test_create_with_explicit_slug_keeps_it(self):
        """A client-supplied slug is used verbatim."""
        response = self.client.post(self.url, {**self.payload, 'slug': 'custom-slug'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['slug'], 'custom-slug')

    def test_duplicate_title_gets_suffixed_slug(self):
        """Two events with the same title do not collide on the unique slug column."""
        first = self.client.post(self.url, self.payload, format='json')
        second = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED, second.data)
        self.assertEqual(first.data['slug'], 'golden-gate-park-hunt')
        self.assertEqual(second.data['slug'], 'golden-gate-park-hunt-2')

    def test_duplicate_explicit_slug_is_rejected(self):
        """Supplying a slug that already exists returns a validation error, not a 500."""
        self.client.post(self.url, {**self.payload, 'slug': 'taken'}, format='json')
        response = self.client.post(self.url, {**self.payload, 'slug': 'taken'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('slug', response.data)


# A trimmed pretalx/frab schedule export: two days, three rooms, three talks.
FRAB_SCHEDULE_FIXTURE = {
    "schedule": {
        "version": "1.0",
        "conference": {
            "acronym": "foss4g-na-2026",
            "title": "FOSS4G NA 2026",
            "days": [
                {
                    "index": 1,
                    "date": "2026-11-03",
                    "rooms": {
                        "Ballroom B": [{
                            "code": "TREES1",
                            "title": "Empowering people to map the urban heat island effect",
                            "persons": [{"public_name": "A. Joseph"}],
                            "start": "16:00",
                            "date": "2026-11-03T16:00:00-08:00",
                            "duration": "00:30",
                            "room": "Ballroom B",
                            "track": "Climate",
                            "url": "https://talks.example.org/foss4g-na-2026/talk/TREES1/",
                            "type": "Talk",
                        }],
                        "Ballroom A": [{
                            "code": "GDAL01",
                            "title": "Code is liability",
                            "persons": [{"public_name": "Howard Butler"}, {"public_name": "Co Speaker"}],
                            "start": "11:00",
                            "date": "2026-11-03T11:00:00-08:00",
                            "duration": "00:30",
                            "room": "Ballroom A",
                            "track": None,
                            "url": "https://talks.example.org/foss4g-na-2026/talk/GDAL01/",
                            "type": "Talk",
                        }],
                    },
                },
                {
                    "index": 2,
                    "date": "2026-11-04",
                    "rooms": {
                        "Room 1": [{
                            "code": "OHM001",
                            "title": "OpenHistoricalMap: across the geoverse",
                            "persons": [{"public_name": "Minh Nguyễn"}],
                            "start": "11:00",
                            "date": "2026-11-04T11:00:00-08:00",
                            "duration": "00:30",
                            "room": "Room 1",
                            "track": "Community",
                            "url": "https://talks.example.org/foss4g-na-2026/talk/OHM001/",
                            "type": "Talk",
                        }],
                    },
                },
            ],
        },
    }
}

SCHEDULE_URL = "https://talks.osgeo.org/foss4g-na-2026/schedule/export/schedule.json"


class EventLeaderboardAndSessionsAPITests(TestCase):
    """
    Validates the leaderboard ranking and the conference schedule (sessions) endpoint.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        polygon = Polygon([
            (-121.51, 38.57), (-121.48, 38.57), (-121.48, 38.59), (-121.51, 38.59), (-121.51, 38.57),
        ])
        now = datetime.now(timezone.utc)
        self.event = Event.objects.create(
            title="FOSS4G NA 2026", hashtag="FOSS4GNA2026", bounding_polygon=polygon,
            start_time=now, end_time=now + timedelta(days=3), schedule_url=SCHEDULE_URL,
        )

    def test_leaderboard_orders_by_score_then_name(self):
        zeta = Team.objects.create(event=self.event, name="Zeta", score=50)
        alpha = Team.objects.create(event=self.event, name="Alpha", score=50)
        low = Team.objects.create(event=self.event, name="Beta", score=5)
        TeamMembership.objects.create(team=alpha, user_identifier="u1")
        TeamMembership.objects.create(team=alpha, user_identifier="u2")
        q1 = Quest.objects.create(event=self.event, title="Q1", description="d")
        q2 = Quest.objects.create(event=self.event, title="Q2", description="d")
        QuestProgress.objects.create(team=alpha, quest=q1, count=1, completed_at=datetime.now(timezone.utc))
        QuestProgress.objects.create(team=alpha, quest=q2, count=1)  # started, not complete

        # A team from another event must not appear.
        other = Event.objects.create(
            title="Other", hashtag="Other", bounding_polygon=self.event.bounding_polygon,
            start_time=self.event.start_time, end_time=self.event.end_time,
        )
        Team.objects.create(event=other, name="Elsewhere", score=999)

        response = self.client.get(reverse('events:event-leaderboard', kwargs={'pk': self.event.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['name'] for row in response.data], ["Alpha", "Zeta", "Beta"])
        self.assertEqual(response.data[0], {
            'id': alpha.id, 'name': 'Alpha', 'score': 50, 'member_count': 2, 'completed_quests': 1,
        })
        self.assertEqual(response.data[1]['member_count'], 0)
        self.assertEqual(response.data[1]['completed_quests'], 0)
        self.assertEqual(response.data[1]['id'], zeta.id)
        self.assertEqual(response.data[2]['id'], low.id)

    @patch('apps.events.services.schedule.requests.get')
    def test_sessions_flattens_frab_schedule(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=FRAB_SCHEDULE_FIXTURE))
        response = self.client.get(reverse('events:event-sessions', kwargs={'pk': self.event.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([s['code'] for s in response.data], ["GDAL01", "TREES1", "OHM001"])
        self.assertEqual(response.data[0], {
            'code': 'GDAL01',
            'title': 'Code is liability',
            'speakers': ['Howard Butler', 'Co Speaker'],
            'start': '2026-11-03T11:00:00-08:00',
            'room': 'Ballroom A',
            'track': None,
            'url': 'https://talks.example.org/foss4g-na-2026/talk/GDAL01/',
            'type': 'Talk',
        })
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], SCHEDULE_URL)
        self.assertEqual(kwargs['timeout'], 15)
        self.assertIn('AdventureTogether', kwargs['headers']['User-Agent'])

    @patch('apps.events.services.schedule.requests.get')
    def test_sessions_are_cached_per_url(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=FRAB_SCHEDULE_FIXTURE))
        url = reverse('events:event-sessions', kwargs={'pk': self.event.id})
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(mock_get.call_count, 1)

    def test_sessions_without_schedule_url_returns_400(self):
        self.event.schedule_url = ''
        self.event.save()
        response = self.client.get(reverse('events:event-sessions', kwargs={'pk': self.event.id}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.events.services.schedule.requests.get')
    def test_sessions_network_failure_returns_502(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("boom")
        response = self.client.get(reverse('events:event-sessions', kwargs={'pk': self.event.id}))
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    @patch('apps.events.services.schedule.requests.get')
    def test_sessions_http_error_returns_502_and_is_not_cached(self, mock_get):
        failing = MagicMock(status_code=500)
        failing.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = failing
        url = reverse('events:event-sessions', kwargs={'pk': self.event.id})
        self.assertEqual(self.client.get(url).status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(mock_get.call_count, 2)

    @patch('apps.events.services.schedule.requests.get')
    def test_sessions_malformed_json_returns_502(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value={"not": "frab"}))
        response = self.client.get(reverse('events:event-sessions', kwargs={'pk': self.event.id}))
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_event_api_exposes_schedule_url(self):
        response = self.client.get(reverse('events:event-detail', kwargs={'pk': self.event.id}))
        self.assertEqual(response.data['schedule_url'], SCHEDULE_URL)


@override_settings(SCHEDULE_URL_ALLOWED_HOSTS=['talks.osgeo.org', 'pretalx.com'])
class ScheduleUrlAllowlistTests(TestCase):
    """
    Event.schedule_url is client-writable and fetched server-side, so only https URLs on
    allowlisted hosts (or their subdomains) are accepted and fetched.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        now = datetime.now(timezone.utc)
        self.event_data = {
            'title': 'Allowlist Hunt',
            'hashtag': 'AllowlistHunt',
            'bounding_polygon': Polygon.from_bbox((-121.51, 38.57, -121.48, 38.59)).geojson,
            'start_time': now.isoformat(),
            'end_time': (now + timedelta(days=1)).isoformat(),
        }

    def create_event(self, schedule_url):
        return self.client.post(reverse('events:event-list'), dict(self.event_data, schedule_url=schedule_url),
                                format='json')

    def test_allowed_host_and_subdomain_pass(self):
        self.assertIsNone(schedule_url_error(SCHEDULE_URL))
        self.assertIsNone(schedule_url_error('https://pretalx.com/foss4g/schedule/export/schedule.json'))
        self.assertIsNone(schedule_url_error('https://cfp.pretalx.com/foss4g/schedule.json'))
        self.assertEqual(self.create_event(SCHEDULE_URL).status_code, status.HTTP_201_CREATED)
        response = self.create_event('https://cfp.pretalx.com/foss4g/schedule.json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_blank_schedule_url_is_allowed(self):
        self.assertEqual(self.create_event('').status_code, status.HTTP_201_CREATED)

    def test_disallowed_host_is_rejected(self):
        for url in ('https://evil.example.com/schedule.json',
                    'https://evilpretalx.com/schedule.json',              # suffix, not a subdomain
                    'https://talks.osgeo.org.evil.example/schedule.json',
                    'https://talks.osgeo.org@evil.example/schedule.json'):  # userinfo trick
            self.assertIn('not allowed', schedule_url_error(url), url)
        response = self.create_event('https://evil.example.com/schedule.json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('schedule_url', response.data)

    def test_http_scheme_is_rejected(self):
        self.assertEqual(schedule_url_error('http://talks.osgeo.org/schedule.json'), 'Schedule URL must use https.')
        self.assertEqual(self.create_event('http://talks.osgeo.org/schedule.json').status_code,
                         status.HTTP_400_BAD_REQUEST)

    @patch('apps.events.services.schedule.requests.get')
    def test_private_ip_is_rejected_without_fetching(self, mock_get):
        for url in ('https://10.0.0.5/schedule.json', 'https://169.254.169.254/latest/meta-data/',
                    'https://[::1]/schedule.json'):
            self.assertIsNotNone(schedule_url_error(url), url)
            with self.assertRaises(ScheduleFetchError):
                fetch_schedule_sessions(url)
        self.assertEqual(self.create_event('https://127.0.0.1/schedule.json').status_code,
                         status.HTTP_400_BAD_REQUEST)
        mock_get.assert_not_called()

    @patch('apps.events.services.schedule.requests.get')
    def test_stored_disallowed_url_is_refused_by_sessions_endpoint(self, mock_get):
        now = datetime.now(timezone.utc)
        event = Event.objects.create(
            title='Legacy', hashtag='Legacy', bounding_polygon=Polygon.from_bbox((-121.51, 38.57, -121.48, 38.59)),
            start_time=now, end_time=now + timedelta(days=1), schedule_url='https://internal.example/x.json',
        )
        response = self.client.get(reverse('events:event-sessions', kwargs={'pk': event.id}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not allowed', response.data['error'])
        mock_get.assert_not_called()

    @patch('apps.events.services.schedule.requests.get')
    def test_redirect_to_disallowed_host_is_refused(self, mock_get):
        mock_get.return_value = MagicMock(status_code=302, headers={'Location': 'https://10.0.0.5/schedule.json'})
        with self.assertRaises(ScheduleFetchError) as ctx:
            fetch_schedule_sessions(SCHEDULE_URL)
        self.assertIn('redirect', str(ctx.exception))
        self.assertEqual(mock_get.call_count, 1)
        self.assertFalse(mock_get.call_args.kwargs['allow_redirects'])

    @patch('apps.events.services.schedule.requests.get')
    def test_redirect_within_allowlist_is_followed(self, mock_get):
        mock_get.side_effect = [
            MagicMock(status_code=301, headers={'Location': '/foss4g-na-2026/schedule/export/schedule.json'}),
            MagicMock(status_code=200, json=MagicMock(return_value=FRAB_SCHEDULE_FIXTURE)),
        ]
        sessions = fetch_schedule_sessions('https://talks.osgeo.org/foss4g-na-2026/schedule.json')
        self.assertEqual(len(sessions), 3)
        self.assertEqual(mock_get.call_args.args[0], SCHEDULE_URL)
