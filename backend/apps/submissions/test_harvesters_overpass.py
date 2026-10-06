"""
Tests for the Overpass-based OSM / OHM harvester, hashtag matching, and team attribution.
No network: requests.get / requests.post are patched with recorded-shape payloads.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests
from django.contrib.gis.geos import Point, Polygon
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import QuestProgress, Submission
from apps.submissions.services.harvest_common import HarvestContext, upsert_submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.submissions.services.overpass_harvester import (
    build_area_filter,
    build_overpass_query,
    build_quest_query,
    build_tag_filters,
)
from apps.submissions.services.progress import set_submission_verification
from apps.submissions.services.tag_matcher import hashtag_matches, match_author_to_team
from apps.teams.models import Team, TeamMembership

FAKE_OVERPASS = 'https://overpass.private.invalid/api/interpreter'


def fake_response(payload, status=200, url=FAKE_OVERPASS):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        err = requests.HTTPError(f'{status} Server Error for url: {url}')
        err.response = resp
        resp.raise_for_status.side_effect = err
    return resp


def overpass_payload(elements):
    return {'version': 0.6, 'generator': 'Overpass API', 'elements': elements}


CAFE_NODE = {
    'type': 'node', 'id': 1001, 'lat': 38.5801, 'lon': -121.4902,
    'timestamp': '2026-11-03T18:02:00Z', 'version': 7, 'changeset': 5001,
    'user': 'mapper_alice', 'uid': 11,
    'tags': {'amenity': 'cafe', 'name': 'Temple', 'opening_hours': 'Mo-Su 06:00-22:00'},
}
CAFE_WAY = {
    'type': 'way', 'id': 1002, 'center': {'lat': 38.5795, 'lon': -121.4911},
    'timestamp': '2026-11-03T18:03:00Z', 'version': 3, 'changeset': 5001,
    'user': 'mapper_alice', 'uid': 11, 'nodes': [1, 2, 3],
    'tags': {'amenity': 'cafe', 'opening_hours': 'Mo-Fr 07:00-15:00'},
}
OTHER_NODE = {
    'type': 'node', 'id': 1003, 'lat': 38.5810, 'lon': -121.4920,
    'timestamp': '2026-11-03T19:00:00Z', 'version': 2, 'changeset': 5002,
    'user': 'somebody', 'uid': 12,
    'tags': {'amenity': 'cafe', 'opening_hours': '24/7'},
}


def changeset_payload(cs_id, user, created_at, tags, closed_at=None):
    cs = {'id': cs_id, 'created_at': created_at, 'open': closed_at is None,
          'comments_count': 0, 'changes_count': 2, 'uid': 11, 'user': user, 'tags': tags}
    if closed_at:
        cs['closed_at'] = closed_at
    return {'version': '0.6', 'generator': 'OpenStreetMap server', 'changeset': cs}


CHANGESETS = {
    5001: changeset_payload(5001, 'mapper_alice', '2026-11-03T18:00:00Z',
                            {'comment': 'Added opening hours', 'hashtags': '#FOSS4GNA2026;#StreetComplete',
                             'created_by': 'StreetComplete 63.4'},
                            closed_at='2026-11-03T18:05:00Z'),
    5002: changeset_payload(5002, 'somebody', '2026-11-03T18:30:00Z',
                            {'comment': 'Fixed hours'}, closed_at='2026-11-03T18:31:00Z'),
}


class FakeApis:
    """Routes patched requests calls; records them for assertions."""

    def __init__(self, elements, changesets=None, overpass_status=200):
        self.elements = elements
        self.changesets = changesets if changesets is not None else CHANGESETS
        self.overpass_status = overpass_status
        self.posts = []
        self.gets = []

    def post(self, url, data=None, **kwargs):
        self.posts.append({'url': url, 'query': (data or {}).get('data'), 'kwargs': kwargs})
        return fake_response(overpass_payload(self.elements), status=self.overpass_status, url=url)

    def get(self, url, **kwargs):
        self.gets.append(url)
        cs_id = int(url.rstrip('/').split('/')[-1].split('.')[0])
        return fake_response(self.changesets[cs_id], url=url)


def make_event(**kwargs):
    defaults = dict(
        title='FOSS4G NA 2026 Open Data Hunt',
        hashtag='FOSS4GNA2026',
        bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
        start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


@override_settings(OVERPASS_URL=FAKE_OVERPASS)
class OverpassHarvesterTests(TestCase):

    def setUp(self):
        cache.clear()
        self.event = make_event()
        self.team = Team.objects.create(event=self.event, name='Cafe Crew')
        TeamMembership.objects.create(team=self.team, user_identifier='device-1',
                                      display_name='Alice', osm_username='Mapper_Alice')
        self.quest = Quest.objects.create(
            event=self.event, title='Farm-to-fork hours', description='Add hours',
            criteria_type='osm_tags', points_reward=40,
            validation_rules={'required_tags': {'amenity': 'cafe', 'opening_hours': '*'},
                              'target_count': 3},
        )

    def run_harvest(self, apis):
        with patch('requests.post', side_effect=apis.post), patch('requests.get', side_effect=apis.get):
            return harvest_event_submissions(self.event.id)

    # --- query building ---

    def test_tag_filters(self):
        self.assertEqual(build_tag_filters({'amenity': 'cafe', 'opening_hours': '*'}),
                         '["amenity"="cafe"]["opening_hours"]')
        self.assertEqual(build_tag_filters({'amenity': 'restaurant|cafe'}),
                         '["amenity"~"^(restaurant|cafe)$"]')
        self.assertEqual(build_tag_filters({'name': 'Say "hi"'}), '["name"="Say \\"hi\\""]')

    def test_query_for_null_geometry_uses_event_polygon(self):
        query = build_quest_query(self.event, self.quest)
        self.assertTrue(query.startswith('[out:json][timeout:60];'))
        self.assertIn('nwr["amenity"="cafe"]["opening_hours"](poly:"38.5720000 -121.5090000 ', query)
        self.assertIn('(newer:"2026-11-02T16:00:00Z")', query)
        self.assertTrue(query.endswith('out meta center;'))

    def test_point_target_uses_around_with_radius(self):
        self.quest.target_geometry = Point(-121.4905, 38.5800, srid=4326)
        self.assertEqual(build_area_filter(self.event, self.quest), '(around:300,38.5800000,-121.4905000)')
        self.quest.validation_rules['radius_m'] = 400
        self.assertEqual(build_area_filter(self.event, self.quest), '(around:400,38.5800000,-121.4905000)')

    def test_polygon_target_and_window_start(self):
        self.quest.target_geometry = Polygon.from_bbox((-121.50, 38.575, -121.48, 38.585))
        self.quest.window_start = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
        query = build_quest_query(self.event, self.quest)
        self.assertIn('(poly:"38.5750000 -121.5000000 38.5850000 -121.5000000 38.5850000 -121.4800000 '
                      '38.5750000 -121.4800000")', query)
        self.assertIn('(newer:"2026-11-03T15:00:00Z")', query)

    def test_build_overpass_query_shape(self):
        q = build_overpass_query({'natural': 'tree'}, '(around:50,1.0000000,2.0000000)', '2026-06-01T00:00:00Z')
        self.assertEqual(q, '[out:json][timeout:60];\nnwr["natural"="tree"](around:50,1.0000000,2.0000000)'
                            '(newer:"2026-06-01T00:00:00Z");\nout meta center;')

    # --- harvesting ---

    def test_harvest_creates_submission_per_changeset_and_quest(self):
        apis = FakeApis([CAFE_NODE, CAFE_WAY, OTHER_NODE])
        stats = self.run_harvest(apis)

        self.assertEqual(stats['osm'], {'harvested': 1, 'created': 1, 'updated': 0, 'matched': 1, 'errors': 0})
        self.assertEqual(stats['summary']['created'], 1)
        sub = Submission.objects.get(platform='osm')
        self.assertEqual(sub.external_id, f'5001/q{self.quest.id}')
        self.assertEqual(sub.external_url, 'https://www.openstreetmap.org/changeset/5001')
        self.assertEqual(sub.author_username, 'mapper_alice')
        self.assertEqual(sub.team, self.team)  # via osm_username, case-insensitive
        self.assertEqual(sub.quest, self.quest)
        self.assertEqual(sub.element_count, 2)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 18, 5, tzinfo=timezone.utc))
        self.assertEqual(sub.diff_payload['changeset']['hashtags'], '#FOSS4GNA2026;#StreetComplete')
        way = [e for e in sub.diff_payload['elements'] if e['type'] == 'way'][0]
        self.assertEqual((way['lat'], way['lon']), (38.5795, -121.4911))
        self.assertEqual(way['version'], 3)

        # Overpass call shape: POST data=, timeout 90, User-Agent
        self.assertEqual(len(apis.posts), 1)
        self.assertEqual(apis.posts[0]['kwargs']['timeout'], 90)
        self.assertIn('User-Agent', apis.posts[0]['kwargs']['headers'])

    def test_changeset_fetched_once_per_run_across_quests(self):
        Quest.objects.create(
            event=self.event, title='Any hours', description='x', criteria_type='osm_tags',
            validation_rules={'required_tags': {'opening_hours': '*'}},
        )
        apis = FakeApis([CAFE_NODE, CAFE_WAY])
        stats = self.run_harvest(apis)
        self.assertEqual(stats['osm']['created'], 2)
        self.assertEqual(len(apis.posts), 2)
        self.assertEqual(len(apis.gets), 1)

    def test_closed_changesets_are_cached_across_runs(self):
        self.run_harvest(FakeApis([CAFE_NODE]))
        apis = FakeApis([CAFE_NODE])
        self.run_harvest(apis)
        self.assertEqual(apis.gets, [])

    def test_comment_hashtag_counts_when_no_hashtags_tag(self):
        changesets = dict(CHANGESETS)
        changesets[5001] = changeset_payload(5001, 'mapper_alice', '2026-11-03T18:00:00Z',
                                             {'comment': 'Hours for #foss4gna2026 hunt'},
                                             closed_at='2026-11-03T18:05:00Z')
        stats = self.run_harvest(FakeApis([CAFE_NODE], changesets))
        self.assertEqual(stats['osm']['created'], 1)

    def test_changeset_before_event_window_is_skipped(self):
        changesets = dict(CHANGESETS)
        changesets[5001] = changeset_payload(5001, 'mapper_alice', '2026-11-01T18:00:00Z',
                                             {'hashtags': '#FOSS4GNA2026'}, closed_at='2026-11-01T18:05:00Z')
        stats = self.run_harvest(FakeApis([CAFE_NODE], changesets))
        self.assertEqual(stats['osm']['created'], 0)

    def test_quest_window_is_enforced(self):
        self.quest.window_end = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
        self.quest.save()
        stats = self.run_harvest(FakeApis([CAFE_NODE]))
        self.assertEqual(stats['osm']['created'], 0)

    def test_require_hashtag_false_accepts_untagged_changesets(self):
        self.quest.validation_rules['require_hashtag'] = False
        self.quest.save()
        stats = self.run_harvest(FakeApis([CAFE_NODE, OTHER_NODE]))
        self.assertEqual(stats['osm']['created'], 2)
        unmatched = Submission.objects.get(external_id=f'5002/q{self.quest.id}')
        self.assertIsNone(unmatched.team)
        self.assertEqual(stats['osm']['matched'], 1)

    def test_reharvest_updates_count_and_advances_verified_progress(self):
        self.run_harvest(FakeApis([CAFE_NODE, CAFE_WAY]))
        sub = Submission.objects.get(platform='osm')
        set_submission_verification(sub, True, 'host')
        self.assertEqual(QuestProgress.objects.get(team=self.team, quest=self.quest).count, 2)

        third = dict(CAFE_NODE, id=1004, lat=38.5803)
        stats = self.run_harvest(FakeApis([CAFE_NODE, CAFE_WAY, third]))
        self.assertEqual(stats['osm']['updated'], 1)
        self.assertEqual(stats['osm']['created'], 0)
        sub.refresh_from_db()
        self.assertEqual(sub.element_count, 3)
        self.assertEqual(len(sub.diff_payload['elements']), 3)
        progress = QuestProgress.objects.get(team=self.team, quest=self.quest)
        self.assertEqual(progress.count, 3)
        self.assertTrue(progress.is_completed)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 40)

        # Unchanged on the next run.
        stats = self.run_harvest(FakeApis([CAFE_NODE, CAFE_WAY, third]))
        self.assertEqual(stats['osm']['updated'], 0)

    def test_reharvest_backfills_team_when_username_added_later(self):
        TeamMembership.objects.update(osm_username='')
        self.run_harvest(FakeApis([CAFE_NODE]))
        self.assertIsNone(Submission.objects.get(platform='osm').team)
        TeamMembership.objects.update(osm_username='mapper_alice')
        stats = self.run_harvest(FakeApis([CAFE_NODE]))
        self.assertEqual(stats['osm']['updated'], 1)
        self.assertEqual(Submission.objects.get(platform='osm').team, self.team)

    @override_settings(OVERPASS_URL='')
    def test_missing_overpass_url_skips_without_public_fallback(self):
        apis = FakeApis([CAFE_NODE])
        with self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = self.run_harvest(apis)
        self.assertEqual(apis.posts, [])
        self.assertEqual(stats['osm']['created'], 0)
        self.assertTrue(any('OVERPASS_URL is not configured' in w for w in stats['warnings']))
        self.assertTrue(any('OVERPASS_URL is not configured' in m for m in logs.output))

    def test_overpass_failure_is_counted_and_never_leaks_url(self):
        apis = FakeApis([CAFE_NODE], overpass_status=504)
        with self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = self.run_harvest(apis)
        self.assertEqual(stats['osm']['errors'], 1)
        self.assertNotIn(FAKE_OVERPASS, json.dumps(stats))
        self.assertNotIn('overpass.private', '\n'.join(logs.output))
        self.assertIn('HTTPError (HTTP 504)', '\n'.join(logs.output))

    def test_connection_error_does_not_leak_url(self):
        def boom(url, **kwargs):
            raise requests.ConnectionError(f'Max retries exceeded with url: {url}')
        with patch('requests.post', side_effect=boom), \
                self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['osm']['errors'], 1)
        self.assertNotIn('overpass.private', json.dumps(stats) + '\n'.join(logs.output))

    def test_overpass_runtime_error_remark(self):
        def post(url, **kwargs):
            return fake_response({'elements': [], 'remark': 'runtime error: Query timed out in "query"'})
        with patch('requests.post', side_effect=post), self.assertLogs('apps.submissions.harvest'):
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['osm']['errors'], 1)

    def test_dry_run_writes_nothing(self):
        apis = FakeApis([CAFE_NODE, CAFE_WAY])
        with patch('requests.post', side_effect=apis.post), patch('requests.get', side_effect=apis.get):
            stats = harvest_event_submissions(self.event.id, dry_run=True)
        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(stats['would_submit'], [{
            'platform': 'osm', 'external_id': f'5001/q{self.quest.id}', 'author': 'mapper_alice',
            'element_count': 2, 'quest': self.quest.id, 'team': self.team.id, 'action': 'create',
        }])


@override_settings(OHM_OVERPASS_URL='https://ohm-overpass.invalid/api/interpreter',
                   OHM_API_BASE='https://ohm.invalid/api/0.6', OVERPASS_URL='')
class OhmHarvesterTests(TestCase):

    def setUp(self):
        cache.clear()
        self.event = make_event()
        self.quest = Quest.objects.create(
            event=self.event, title='Alkali Flat then and now', description='x',
            criteria_type='ohm_feature', validation_rules={},
            target_geometry=Polygon.from_bbox((-121.495, 38.582, -121.485, 38.590)),
        )

    def test_ohm_uses_ohm_endpoints_and_start_date_default(self):
        building = {
            'type': 'way', 'id': 77, 'center': {'lat': 38.585, 'lon': -121.49},
            'timestamp': '2026-11-04T19:00:00Z', 'version': 1, 'changeset': 900, 'user': 'histmapper',
            'tags': {'building': 'house', 'start_date': '1885'},
        }
        apis = FakeApis([building], {900: changeset_payload(
            900, 'histmapper', '2026-11-04T18:50:00Z', {'comment': 'Alkali Flat #FOSS4GNA2026'})})
        with patch('requests.post', side_effect=apis.post), patch('requests.get', side_effect=apis.get):
            stats = harvest_event_submissions(self.event.id)

        self.assertEqual(apis.posts[0]['url'], 'https://ohm-overpass.invalid/api/interpreter')
        self.assertIn('nwr["start_date"](poly:', apis.posts[0]['query'])
        self.assertEqual(apis.gets, ['https://ohm.invalid/api/0.6/changeset/900.json'])
        self.assertEqual(stats['ohm']['created'], 1)
        self.assertNotIn('osm', stats)
        sub = Submission.objects.get(platform='ohm')
        self.assertEqual(sub.external_url, 'https://www.openhistoricalmap.org/changeset/900')
        # Open changeset: contributed_at falls back to created_at.
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 4, 18, 50, tzinfo=timezone.utc))


class HashtagMatchingTests(TestCase):

    def test_hashtags_tag_is_split_on_semicolons(self):
        self.assertTrue(hashtag_matches({'hashtags': '#MapLibre;#foss4gna2026'}, 'FOSS4GNA2026'))
        self.assertTrue(hashtag_matches({'hashtags': 'FOSS4GNA2026'}, '#FOSS4GNA2026'))
        self.assertFalse(hashtag_matches({'hashtags': '#FOSS4GNA2026hunt'}, 'FOSS4GNA2026'))

    def test_comment_fallback_and_whole_token(self):
        self.assertTrue(hashtag_matches({'comment': 'hours #FOSS4GNA2026'}, 'FOSS4GNA2026'))
        self.assertTrue(hashtag_matches('Closing (#foss4gna2026).', 'FOSS4GNA2026'))
        self.assertFalse(hashtag_matches('FOSS4GNA2026 without hash', 'FOSS4GNA2026'))
        self.assertFalse(hashtag_matches('#FOSS4GNA20267', 'FOSS4GNA2026'))
        self.assertFalse(hashtag_matches('', 'FOSS4GNA2026'))
        self.assertFalse(hashtag_matches({'comment': 'x'}, ''))


class MatchAuthorToTeamTests(TestCase):

    def setUp(self):
        self.event = make_event()
        self.red = Team.objects.create(event=self.event, name='Red')
        self.blue = Team.objects.create(event=self.event, name='Blue')
        TeamMembership.objects.create(team=self.red, user_identifier='device-r', display_name='sam',
                                      osm_username='', wikimedia_username='', github_username='')
        TeamMembership.objects.create(team=self.blue, user_identifier='device-b', display_name='Blue Bea',
                                      osm_username='SAM', wikimedia_username='SamWiki', github_username='sam-gh')

    def test_platform_username_takes_precedence(self):
        self.assertEqual(match_author_to_team(self.event, 'sam', 'osm'), self.blue)
        self.assertEqual(match_author_to_team(self.event, 'sam', 'ohm'), self.blue)
        self.assertEqual(match_author_to_team(self.event, 'sam', 'osm_notes'), self.blue)
        self.assertEqual(match_author_to_team(self.event, 'samwiki', 'commons'), self.blue)
        self.assertEqual(match_author_to_team(self.event, 'SamWiki', 'wikidata'), self.blue)
        self.assertEqual(match_author_to_team(self.event, 'SAM-GH', 'github'), self.blue)

    def test_falls_back_to_identifier_and_display_name(self):
        self.assertEqual(match_author_to_team(self.event, 'sam', 'github'), self.red)
        self.assertEqual(match_author_to_team(self.event, 'sam'), self.red)
        self.assertEqual(match_author_to_team(self.event, 'DEVICE-B', 'commons'), self.blue)
        self.assertIsNone(match_author_to_team(self.event, 'nobody', 'osm'))
        self.assertIsNone(match_author_to_team(self.event, '', 'osm'))

    def test_other_events_are_ignored(self):
        other = make_event(title='Other', hashtag='Other')
        self.assertIsNone(match_author_to_team(other, 'sam', 'osm'))


class UpsertSubmissionTeamMatchingTests(TestCase):
    """upsert_submission looks each author up once per run, and not at all for credited submissions."""

    def setUp(self):
        self.event = make_event()
        self.team = Team.objects.create(event=self.event, name='Red')
        TeamMembership.objects.create(team=self.team, user_identifier='device-r', osm_username='Alice')
        self.quest = Quest.objects.create(event=self.event, title='Cafes', description='d')

    def membership_queries(self, ctx, external_ids, author):
        with CaptureQueriesContext(connection) as queries:
            for external_id in external_ids:
                upsert_submission(
                    ctx, platform='osm', quest=self.quest, external_id=external_id,
                    external_url=f'https://www.openstreetmap.org/changeset/{external_id}',
                    author_username=author, contributed_at=self.event.start_time,
                )
        return sum('teams_teammembership' in q['sql'] for q in queries.captured_queries)

    def test_same_author_is_matched_once_per_run(self):
        ctx = HarvestContext(event=self.event)
        one = self.membership_queries(ctx, ['1'], 'alice')
        many = self.membership_queries(ctx, ['2', '3', '4', '5'], 'ALICE')
        self.assertGreater(one, 0)
        self.assertEqual(many, 0)
        self.assertEqual(Submission.objects.filter(team=self.team).count(), 5)

    def test_unmatched_author_is_cached_too(self):
        ctx = HarvestContext(event=self.event)
        self.membership_queries(ctx, ['1'], 'stranger')
        self.assertEqual(self.membership_queries(ctx, ['2', '3'], 'stranger'), 0)
        self.assertFalse(Submission.objects.filter(team__isnull=False).exists())

    def test_existing_credited_submission_skips_matching(self):
        self.membership_queries(HarvestContext(event=self.event), ['1'], 'alice')
        # A fresh run (empty cache) re-seeing an already-credited submission does no lookup.
        self.assertEqual(self.membership_queries(HarvestContext(event=self.event), ['1'], 'alice'), 0)

    def test_existing_uncredited_submission_is_credited_on_a_later_run(self):
        self.membership_queries(HarvestContext(event=self.event), ['1'], 'bob')
        TeamMembership.objects.create(team=self.team, user_identifier='device-b', osm_username='bob')
        self.membership_queries(HarvestContext(event=self.event), ['1'], 'bob')
        self.assertEqual(Submission.objects.get(external_id='1').team, self.team)
