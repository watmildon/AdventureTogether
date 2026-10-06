"""
Unit and Integration Tests for Quests, Criteria Rules, and Geometry Containment.
"""

from datetime import datetime, timezone, timedelta
from django.contrib.gis.geos import Polygon, Point
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.events.models import Event
from .models import Quest


class QuestValidationAndAPITests(TestCase):
    """
    Validates Quest geometry validation against event bounds and REST endpoints.
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
            title="Downtown Mapping Challenge",
            hashtag="DowntownMap",
            bounding_polygon=self.sf_polygon,
            start_time=now,
            end_time=now + timedelta(hours=5),
        )
        self.quest = Quest.objects.create(
            event=self.event,
            title="Add Restaurant Opening Hours",
            description="Add opening_hours tag to 5 restaurants.",
            criteria_type="osm_tags",
            validation_rules={
                "required_tags": {
                    "amenity": "restaurant",
                    "opening_hours": "*"
                },
                "target_count": 5
            },
            points_reward=20
        )

    def test_create_quest_within_event_bounds_succeeds(self):
        """Creating quest with target geometry inside bounding polygon succeeds."""
        inside_point = Point(-122.41, 37.77)
        url = reverse('quests:quest-list')
        data = {
            'event': self.event.id,
            'title': 'Map Dolores Park Benches',
            'description': 'Map benches in the park.',
            'criteria_type': 'osm_tags',
            'target_geometry': inside_point.ewkt,
            'validation_rules': {'required_tags': {'amenity': 'bench'}},
            'points_reward': 15
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_quest_outside_event_bounds_rejected(self):
        """Creating quest with target geometry outside bounding polygon returns 400 Bad Request."""
        outside_point = Point(-122.60, 37.90)  # Outside SF polygon
        url = reverse('quests:quest-list')
        data = {
            'event': self.event.id,
            'title': 'Out of Bounds Quest',
            'description': 'This should fail validation.',
            'criteria_type': 'osm_tags',
            'target_geometry': outside_point.ewkt,
            'validation_rules': {'required_tags': {'amenity': 'bench'}}
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('target_geometry', response.data)


class QuestTargetCountAndWindowTests(TestCase):
    """
    Validates the target_count property, quest time windows, and the session-linkage fields.
    """

    def setUp(self):
        self.client = APIClient()
        self.polygon = Polygon([
            (-121.51, 38.57), (-121.48, 38.57), (-121.48, 38.59), (-121.51, 38.59), (-121.51, 38.57),
        ])
        self.now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        self.event = Event.objects.create(
            title="FOSS4G NA Test",
            hashtag="FOSS4GNA2026",
            bounding_polygon=self.polygon,
            start_time=self.now,
            end_time=self.now + timedelta(days=3),
        )

    def make_quest(self, **kwargs):
        defaults = dict(event=self.event, title="Q", description="d", criteria_type="osm_tags")
        defaults.update(kwargs)
        return Quest.objects.create(**defaults)

    def test_target_count_defaults_to_one(self):
        self.assertEqual(self.make_quest().target_count, 1)

    def test_target_count_reads_validation_rules(self):
        self.assertEqual(self.make_quest(validation_rules={"target_count": "5"}).target_count, 5)

    def test_target_count_floors_at_one_and_ignores_garbage(self):
        self.assertEqual(self.make_quest(validation_rules={"target_count": 0}).target_count, 1)
        self.assertEqual(self.make_quest(validation_rules={"target_count": -3}).target_count, 1)
        self.assertEqual(self.make_quest(validation_rules={"target_count": "lots"}).target_count, 1)

    def test_is_open_at_without_window_follows_is_active(self):
        quest = self.make_quest()
        self.assertTrue(quest.is_open_at(self.now))
        quest.is_active = False
        self.assertFalse(quest.is_open_at(self.now))

    def test_is_open_at_respects_window(self):
        start = self.now + timedelta(hours=6)
        end = start + timedelta(hours=2)
        quest = self.make_quest(criteria_type="location_checkin", window_start=start, window_end=end)
        self.assertFalse(quest.is_open_at(start - timedelta(minutes=1)))
        self.assertTrue(quest.is_open_at(start))
        self.assertTrue(quest.is_open_at(end))
        self.assertFalse(quest.is_open_at(end + timedelta(minutes=1)))

    def test_is_open_at_with_only_one_bound(self):
        quest = self.make_quest(window_end=self.now)
        self.assertTrue(quest.is_open_at(self.now - timedelta(days=1)))
        self.assertFalse(quest.is_open_at(self.now + timedelta(seconds=1)))

    def test_create_quest_with_inspired_by_and_window(self):
        inspired_by = {
            "code": "ABC123",
            "title": "OpenHistoricalMap: across the geoverse",
            "speakers": ["Minh Nguyễn"],
            "start": "2026-11-04T11:00:00-08:00",
            "room": "Ballroom A",
            "track": "Community",
            "url": "https://talks.example.org/talk/ABC123/",
        }
        response = self.client.post(reverse('quests:quest-list'), {
            'event': self.event.id,
            'title': 'Icebreaker check-in',
            'description': 'Be at the icebreaker.',
            'criteria_type': 'location_checkin',
            'validation_rules': {'radius_m': 60, 'target_count': 1},
            'inspired_by': inspired_by,
            'window_start': '2026-11-03T02:00:00Z',
            'window_end': '2026-11-03T04:00:00Z',
            'points_reward': 10,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['inspired_by'], inspired_by)
        self.assertEqual(response.data['target_count'], 1)
        quest = Quest.objects.get(pk=response.data['id'])
        self.assertEqual(quest.window_start, datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(quest.inspired_by['speakers'], ["Minh Nguyễn"])

    def test_target_count_is_read_only_in_api(self):
        response = self.client.post(reverse('quests:quest-list'), {
            'event': self.event.id,
            'title': 'Trees',
            'description': 'Map trees.',
            'validation_rules': {'target_count': 10},
            'target_count': 99,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['target_count'], 10)

    def test_inspired_by_must_be_object(self):
        response = self.client.post(reverse('quests:quest-list'), {
            'event': self.event.id,
            'title': 'Bad',
            'description': 'Bad inspired_by.',
            'inspired_by': ['not', 'an', 'object'],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('inspired_by', response.data)

    def test_inverted_window_rejected(self):
        response = self.client.post(reverse('quests:quest-list'), {
            'event': self.event.id,
            'title': 'Backwards',
            'description': 'Window ends before it starts.',
            'window_start': '2026-11-03T04:00:00Z',
            'window_end': '2026-11-03T02:00:00Z',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('window_end', response.data)
