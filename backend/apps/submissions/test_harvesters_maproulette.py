"""
Tests for the MapRoulette harvester (maproulette_task quests). No network: requests.get is
routed to payloads shaped like maproulette.org/api/v2 and OSM changeset API responses.
"""

import copy
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Polygon
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.submissions.services.maproulette_harvester import MAX_PAGES, PAGE_LIMIT
from apps.teams.models import Team, TeamMembership

MR = 'https://maproulette.invalid/api/v2'
OSM_API = 'https://osm.invalid/api/0.6'
BOX_URL = f'{MR}/tasks/box/-121.509000/38.572000/-121.481000/38.590000'


def listed(task_id, status, parent, lat=38.58, lng=-121.49, mapped_on='2026-11-03T18:00:00.000Z',
           completed_by=None, parent_name='Challenge'):
    item = {'id': task_id, 'owner': -1, 'title': f'osm {task_id}', 'parentId': parent, 'parentName': parent_name,
            'point': {'lat': lat, 'lng': lng}, 'modified': mapped_on or '2026-11-03T18:00:00.000Z', 'status': status,
            'priority': 0}
    if mapped_on:
        item['mappedOn'] = mapped_on
    if completed_by:
        item['completedBy'] = completed_by
    return item


def detail(task_id, status, parent, changeset_id=-1, completed_by=None, mapped_on='2026-11-03T18:00:00.000Z'):
    return {'id': task_id, 'name': f'osm {task_id}', 'parent': parent, 'status': status,
            'created': '2026-08-21T17:42:32.557Z', 'modified': mapped_on or '2026-11-03T18:00:00.000Z',
            'mappedOn': mapped_on, 'completedBy': completed_by, 'changesetId': changeset_id,
            'location': {'type': 'Point', 'coordinates': [-121.49, 38.58]}}


LISTING = [
    # Fixed with a recorded changeset that has the hashtag.
    listed(101, 1, 56424, completed_by={'username': 'mr_name', 'id': 900}, parent_name='California Flags'),
    # Already fixed, no changeset: the listing names the completing user.
    listed(102, 5, 42871, completed_by={'username': 'parking_pro', 'id': 901}),
    # False positive: not a default status.
    listed(103, 2, 42871),
    # Mapped before the event: dropped without a detail fetch.
    listed(104, 1, 42871, mapped_on='2026-10-01T10:00:00.000Z'),
    # Outside the event perimeter.
    listed(105, 1, 42871, lat=38.60, lng=-121.40),
    # No mappedOn in the listing; the detail has it. Only a user id is known.
    listed(106, 1, 53620, mapped_on=None),
]

DETAILS = {
    101: detail(101, 1, 56424, changeset_id=7001, completed_by=900),
    102: detail(102, 5, 42871, completed_by=901),
    103: detail(103, 2, 42871, completed_by=1),
    104: detail(104, 1, 42871, completed_by=1, mapped_on='2026-10-01T10:00:00.000Z'),
    105: detail(105, 1, 42871, completed_by=1),
    106: detail(106, 1, 53620, completed_by=903),
}

CHANGESETS = {
    7001: {'changeset': {'id': 7001, 'user': 'osm_flagfan', 'uid': 5, 'open': False,
                         'created_at': '2026-11-03T17:59:00Z', 'closed_at': '2026-11-03T18:00:00Z',
                         'tags': {'comment': 'Flag details #FOSS4GNA2026 #maproulette'}}},
    7002: {'changeset': {'id': 7002, 'user': 'osm_quiet', 'uid': 6, 'open': False,
                         'created_at': '2026-11-03T17:59:00Z', 'closed_at': '2026-11-03T18:00:00Z',
                         'tags': {'comment': 'Parking type #maproulette'}}},
}


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


class FakeApis:
    """Routes requests.get by URL and records the calls."""

    def __init__(self, pages, details=None, users=None):
        self.pages = pages
        self.details = details if details is not None else DETAILS
        self.users = users if users is not None else {}
        self.calls = []

    def get(self, url, headers=None, timeout=None, params=None, **kwargs):
        self.calls.append((url, params))
        if url.startswith(f'{MR}/tasks/box/'):
            page = params['page']
            return ok(self.pages[page] if page < len(self.pages) else [])
        if url.startswith(f'{MR}/task/'):
            return ok(self.details[int(url.rsplit('/', 1)[1])])
        if url.startswith(f'{MR}/user/'):
            return ok(self.users.get(int(url.split('/')[-2]), {}))
        if url.startswith(f'{OSM_API}/changeset/'):
            return ok(CHANGESETS[int(url.rsplit('/', 1)[1].split('.')[0])])
        raise AssertionError(f'unexpected URL {url}')

    def urls(self, prefix):
        return [url for url, _ in self.calls if url.startswith(prefix)]


@override_settings(MAPROULETTE_API=MR, OSM_API_BASE=OSM_API)
class MapRouletteHarvesterTests(TestCase):

    def setUp(self):
        cache.clear()
        self.event = Event.objects.create(
            title='Hunt', hashtag='FOSS4GNA2026',
            bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
            start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        self.flags = Team.objects.create(event=self.event, name='Flags')
        TeamMembership.objects.create(team=self.flags, user_identifier='d1', osm_username='osm_flagfan')
        self.quest = Quest.objects.create(
            event=self.event, title='Clear a MapRoulette task', description='x', criteria_type='maproulette_task',
            validation_rules={'target_count': 3, 'statuses': [1, 5], 'require_hashtag': False},
        )

    def harvest(self, apis=None, dry_run=False):
        apis = apis or FakeApis([LISTING])
        with patch('requests.get', side_effect=apis.get):
            stats = harvest_event_submissions(self.event.id, dry_run=dry_run)
        return stats, apis

    def created_ids(self):
        return {int(eid.split('/')[0]) for eid in Submission.objects.values_list('external_id', flat=True)}

    def test_listing_request_shape(self):
        _, apis = self.harvest()
        url, params = apis.calls[0]
        self.assertEqual(url, BOX_URL)
        self.assertEqual(params, {'limit': PAGE_LIMIT, 'page': 0, 'tStatus': '1,5'})

    def test_status_window_and_area_filters(self):
        stats, apis = self.harvest()
        self.assertEqual(self.created_ids(), {101, 102, 106})
        self.assertEqual(stats['maproulette']['created'], 3)
        self.assertEqual(stats['maproulette']['errors'], 0)
        # Only tasks that passed the listing checks are fetched in full.
        self.assertEqual(stats['maproulette']['detail_lookups'], 3)
        self.assertEqual(sorted(apis.urls(f'{MR}/task/')), [f'{MR}/task/101', f'{MR}/task/102', f'{MR}/task/106'])
        self.assertNotIn('detail_lookups', stats['summary'])

    def test_changeset_attribution(self):
        self.harvest()
        sub = Submission.objects.get(external_id=f'101/q{self.quest.id}')
        self.assertEqual(sub.platform, 'maproulette')
        self.assertEqual(sub.author_username, 'osm_flagfan')
        self.assertEqual(sub.team, self.flags)
        self.assertEqual(sub.external_url, 'https://maproulette.org/challenge/56424/task/101')
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(sub.element_count, 1)
        self.assertEqual(sub.diff_payload['challenge_id'], 56424)
        self.assertEqual(sub.diff_payload['challenge_name'], 'California Flags')
        self.assertEqual(sub.diff_payload['changeset_id'], 7001)
        self.assertEqual(sub.diff_payload['status'], 1)
        self.assertEqual(sub.diff_payload['attributed_by'], 'changeset')

    def test_completed_by_fallbacks(self):
        parking = Team.objects.create(event=self.event, name='Parking')
        TeamMembership.objects.create(team=parking, user_identifier='d2', osm_username='Parking_Pro')
        _, apis = self.harvest()
        listed_name = Submission.objects.get(external_id=f'102/q{self.quest.id}')
        self.assertEqual(listed_name.author_username, 'parking_pro')
        self.assertEqual(listed_name.team, parking)
        self.assertEqual(listed_name.diff_payload['attributed_by'], 'completed_by')
        self.assertIsNone(listed_name.diff_payload['changeset_id'])
        # 106: no username anywhere and an empty public profile -> the MapRoulette user id.
        unknown = Submission.objects.get(external_id=f'106/q{self.quest.id}')
        self.assertEqual(unknown.author_username, 'MapRoulette user 903')
        self.assertEqual(unknown.diff_payload['attributed_by'], 'user_id')
        self.assertEqual(apis.urls(f'{MR}/user/'), [f'{MR}/user/903/public'])

    def test_public_profile_gives_osm_display_name(self):
        users = {903: {'id': 903, 'osmProfile': {'id': 23065625, 'displayName': 'curb_cutter'}, 'name': 'curb_cutter'}}
        self.harvest(FakeApis([LISTING], users=users))
        sub = Submission.objects.get(external_id=f'106/q{self.quest.id}')
        self.assertEqual(sub.author_username, 'curb_cutter')
        self.assertEqual(sub.diff_payload['attributed_by'], 'completed_by')

    def test_require_hashtag_needs_a_changeset_with_it(self):
        self.quest.validation_rules = {'require_hashtag': True}
        self.quest.save()
        details = copy.deepcopy(DETAILS)
        details[102]['changesetId'] = 7002  # a changeset without the hashtag
        stats, _ = self.harvest(FakeApis([LISTING], details=details))
        self.assertEqual(self.created_ids(), {101})

    def test_challenge_filter(self):
        self.quest.validation_rules = {'challenge_ids': [56424]}
        self.quest.save()
        stats, _ = self.harvest()
        self.assertEqual(self.created_ids(), {101})
        self.assertEqual(stats['maproulette']['detail_lookups'], 1)

    def test_custom_statuses(self):
        self.quest.validation_rules = {'statuses': [2]}
        self.quest.save()
        _, apis = self.harvest()
        self.assertEqual(apis.calls[0][1]['tStatus'], '2')
        self.assertEqual(self.created_ids(), {103})

    def test_paging_stops_on_a_short_page(self):
        filler = [listed(1000 + i, 0, 1) for i in range(PAGE_LIMIT)]
        stats, apis = self.harvest(FakeApis([filler, LISTING]))
        self.assertEqual([params['page'] for url, params in apis.calls if url == BOX_URL], [0, 1])
        self.assertEqual(stats['maproulette']['created'], 3)
        self.assertEqual(stats['warnings'], [])

    def test_paging_is_capped(self):
        filler = [listed(1000 + i, 0, 1) for i in range(PAGE_LIMIT)]
        stats, apis = self.harvest(FakeApis([filler] * (MAX_PAGES + 5)))
        self.assertEqual(len(apis.urls(BOX_URL)), MAX_PAGES)
        self.assertTrue(any('MapRoulette' in w for w in stats['warnings']))

    def test_no_refetch_when_unchanged_but_team_still_filled_in(self):
        self.harvest()
        parking = Team.objects.create(event=self.event, name='Parking')
        TeamMembership.objects.create(team=parking, user_identifier='d2', osm_username='parking_pro')

        stats, apis = self.harvest()
        self.assertEqual(stats['maproulette']['detail_lookups'], 0)
        self.assertEqual(apis.urls(f'{MR}/task/'), [])
        self.assertEqual(stats['maproulette']['harvested'], 3)
        self.assertEqual(stats['maproulette']['created'], 0)
        self.assertEqual(stats['maproulette']['updated'], 1)
        self.assertEqual(Submission.objects.get(external_id=f'102/q{self.quest.id}').team, parking)

    def test_refetch_when_mapped_again(self):
        self.harvest()
        listing = copy.deepcopy(LISTING)
        listing[0]['mappedOn'] = '2026-11-04T09:00:00.000Z'
        # 106 has no mappedOn in the listing, so its modified is compared instead.
        listing[5]['modified'] = '2026-11-04T10:00:00.000Z'
        stats, apis = self.harvest(FakeApis([listing]))
        self.assertEqual(sorted(apis.urls(f'{MR}/task/')), [f'{MR}/task/101', f'{MR}/task/106'])
        self.assertEqual(stats['maproulette']['detail_lookups'], 2)

    def test_listing_failure_is_one_error(self):
        resp = MagicMock()
        resp.status_code = 504
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(f'504 for url: {BOX_URL}')
        with patch('requests.get', return_value=resp), self.assertLogs('apps.submissions.harvest') as logs:
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['maproulette']['errors'], 1)
        self.assertNotIn('maproulette.invalid', '\n'.join(logs.output))

    def test_dry_run_writes_nothing(self):
        stats, _ = self.harvest(dry_run=True)
        self.assertEqual(len(stats['would_submit']), 3)
        self.assertFalse(Submission.objects.exists())
