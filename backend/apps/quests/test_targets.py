"""
Tests for GET /api/quests/<id>/targets/ (Wikidata items a wikidata_area quest still needs). No network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests
from django.contrib.gis.geos import Polygon
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.events.models import Event
from apps.quests.models import Quest

SPARQL = 'https://sparql.invalid/sparql'


def binding(qid, lat, lon, label=None):
    row = {
        'item': {'type': 'uri', 'value': f'http://www.wikidata.org/entity/{qid}'},
        'lat': {'type': 'literal', 'value': str(lat)},
        'lon': {'type': 'literal', 'value': str(lon)},
    }
    row['itemLabel'] = {'type': 'literal', 'value': label or qid}
    return row


SPARQL_RESPONSE = {'head': {'vars': ['item', 'itemLabel', 'lat', 'lon']}, 'results': {'bindings': [
    binding('Q100', 38.5799, -121.4940, 'Tower Theatre'),
    binding('Q100', 38.5800, -121.4941, 'Tower Theatre'),   # second P625 value: one target
    binding('Q200', 38.5750, -121.5000, 'Crocker Art Museum'),
    binding('Q300', 38.5850, -121.4850),                      # no English label
]}}


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


@override_settings(WIKIDATA_SPARQL=SPARQL)
class QuestTargetsTests(TestCase):

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.event = Event.objects.create(
            title='Hunt', hashtag='FOSS4GNA2026',
            bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
            start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        self.quest = Quest.objects.create(event=self.event, title='Picture this', description='x',
                                          criteria_type='wikidata_area',
                                          validation_rules={'properties': ['P18'], 'target_count': 3})
        self.calls = []

    def sparql(self, url, params=None, headers=None, timeout=None, **kwargs):
        assert url == SPARQL
        assert headers['User-Agent']
        assert timeout == 60
        self.calls.append(params['query'])
        return ok(SPARQL_RESPONSE)

    def get(self, quest=None):
        with patch('requests.get', side_effect=self.sparql):
            return self.client.get(f'/api/quests/{(quest or self.quest).id}/targets/')

    def test_lists_items_lacking_the_properties_in_the_event_area(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['quest'], self.quest.id)
        self.assertEqual(data['count'], 3)
        self.assertEqual([t['qid'] for t in data['targets']], ['Q200', 'Q300', 'Q100'])
        tower = data['targets'][2]
        self.assertEqual(tower, {
            'qid': 'Q100', 'label': 'Tower Theatre', 'lat': 38.5799, 'lon': -121.494,
            'wikidata_url': 'https://www.wikidata.org/wiki/Q100',
            'wikishootme_url': 'https://wikishootme.toolforge.org/#lat=38.5799&lng=-121.494&zoom=18',
        })
        query = self.calls[0]
        self.assertIn('wikibase:cornerSouthWest "Point(-121.509000 38.572000)"', query)
        self.assertIn('wikibase:cornerNorthEast "Point(-121.481000 38.590000)"', query)
        self.assertIn('FILTER NOT EXISTS { ?item wdt:P18 [] }', query)
        self.assertIn('LIMIT 500', query)

    def test_every_configured_property_must_be_missing(self):
        self.quest.validation_rules = {'properties': ['P18', 'p373', 'bad"}']}
        self.quest.save()
        self.get()
        self.assertIn('FILTER NOT EXISTS { ?item wdt:P18 [] }', self.calls[0])
        self.assertIn('FILTER NOT EXISTS { ?item wdt:P373 [] }', self.calls[0])
        self.assertNotIn('bad', self.calls[0])

    def test_polygon_area_filters_the_box_results(self):
        # A triangle whose box covers all three items but which only contains Q200.
        self.quest.target_geometry = Polygon(((-121.505, 38.573), (-121.495, 38.573), (-121.505, 38.583),
                                              (-121.505, 38.573)), srid=4326)
        self.quest.save()
        data = self.get().json()
        self.assertEqual([t['qid'] for t in data['targets']], ['Q200'])
        self.assertIn('"Point(-121.505000 38.573000)"', self.calls[0])

    def test_results_are_cached_per_quest_and_rules(self):
        self.get()
        self.get()
        self.assertEqual(len(self.calls), 1)
        self.quest.validation_rules = {'properties': ['P373']}
        self.quest.save()
        self.get()
        self.assertEqual(len(self.calls), 2)

    def test_other_quest_types_get_400(self):
        other = Quest.objects.create(event=self.event, title='Any edit', description='x',
                                     criteria_type='wikidata_entry', validation_rules={})
        response = self.get(other)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.calls, [])

    def test_query_service_failure_gives_502_without_the_url(self):
        with patch('requests.get', side_effect=requests.ConnectionError(f'cannot reach {SPARQL}')):
            response = self.client.get(f'/api/quests/{self.quest.id}/targets/')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('invalid', response.json()['error'])
        # Failures are not cached.
        self.get()
        self.assertEqual(len(self.calls), 1)
