"""
Unit and Integration Tests for Event Lifecycle and Spatial Boundary Validation.
"""

from datetime import datetime, timezone, timedelta
from django.contrib.gis.geos import Polygon, Point
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from .models import Event


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
