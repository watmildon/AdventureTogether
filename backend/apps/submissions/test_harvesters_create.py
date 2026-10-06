"""
Tests for `osm_tags` quests with `validation_rules.action` ("create" / "modify"): crediting the
creator of an element through its version 1, the OSM history lookups that needs, and the
TrackedOsmElement rows that keep those lookups to one per element version.
No network: requests.get / requests.post are patched.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.quests.models import Quest
from apps.submissions.models import Submission, TrackedOsmElement
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.teams.models import Team, TeamMembership
from .test_harvesters_overpass import (
    FAKE_OVERPASS,
    changeset_payload,
    fake_response,
    make_event,
    overpass_payload,
)

API_BASE = 'https://osm.invalid/api/0.6'
HASHTAGGED = {'comment': 'Surveyed hydrants #FOSS4GNA2026', 'created_by': 'Every Door'}

# Created by a participant during the event; still at version 1.
NEW_HYDRANT = {
    'type': 'node', 'id': 2001, 'lat': 38.5801, 'lon': -121.4902,
    'timestamp': '2026-11-03T18:02:00Z', 'version': 1, 'changeset': 6001,
    'user': 'mapper_alice', 'uid': 11, 'tags': {'emergency': 'fire_hydrant'},
}
# Created by a participant during the event, then edited twice; last by someone else.
EDITED_AED = {
    'type': 'node', 'id': 2002, 'lat': 38.5805, 'lon': -121.4910,
    'timestamp': '2026-11-04T10:00:00Z', 'version': 3, 'changeset': 7002,
    'user': 'somebody', 'uid': 12, 'tags': {'emergency': 'defibrillator', 'indoor': 'yes'},
}
# Created before the event, edited by a participant during it.
OLD_HYDRANT = {
    'type': 'node', 'id': 2003, 'lat': 38.5810, 'lon': -121.4920,
    'timestamp': '2026-11-03T18:04:00Z', 'version': 2, 'changeset': 6001,
    'user': 'mapper_alice', 'uid': 11, 'tags': {'emergency': 'fire_hydrant', 'colour': 'red'},
}

HISTORIES = {
    ('node', 2002): [
        {'type': 'node', 'id': 2002, 'version': 1, 'timestamp': '2026-11-03T18:03:00Z',
         'user': 'mapper_alice', 'uid': 11, 'changeset': 6001},
        {'type': 'node', 'id': 2002, 'version': 2, 'timestamp': '2026-11-03T20:00:00Z',
         'user': 'mapper_alice', 'uid': 11, 'changeset': 6005},
        {'type': 'node', 'id': 2002, 'version': 3, 'timestamp': '2026-11-04T10:00:00Z',
         'user': 'somebody', 'uid': 12, 'changeset': 7002},
    ],
    ('node', 2003): [
        {'type': 'node', 'id': 2003, 'version': 1, 'timestamp': '2026-10-20T12:00:00Z',
         'user': 'mapper_alice', 'uid': 11, 'changeset': 5900},
        {'type': 'node', 'id': 2003, 'version': 2, 'timestamp': '2026-11-03T18:04:00Z',
         'user': 'mapper_alice', 'uid': 11, 'changeset': 6001},
    ],
}

CHANGESETS = {
    5900: changeset_payload(5900, 'mapper_alice', '2026-10-20T11:58:00Z', HASHTAGGED,
                            closed_at='2026-10-20T12:01:00Z'),
    6001: changeset_payload(6001, 'mapper_alice', '2026-11-03T18:00:00Z', HASHTAGGED,
                            closed_at='2026-11-03T18:05:00Z'),
    7002: changeset_payload(7002, 'somebody', '2026-11-04T09:59:00Z', {'comment': 'Fixed tags'},
                            closed_at='2026-11-04T10:01:00Z'),
}


class FakeOsm:
    """Routes patched requests calls to Overpass, the changeset API and the history API."""

    def __init__(self, elements, histories=None, changesets=None, history_status=200):
        self.elements = elements
        self.histories = histories if histories is not None else HISTORIES
        self.changesets = changesets if changesets is not None else CHANGESETS
        self.history_status = history_status
        self.gets = []

    def post(self, url, data=None, **kwargs):
        return fake_response(overpass_payload(self.elements), url=url)

    def get(self, url, **kwargs):
        self.gets.append(url)
        parts = url.split('/')
        if url.endswith('/history.json'):
            key = (parts[-3], int(parts[-2]))
            return fake_response({'version': '0.6', 'elements': self.histories.get(key, [])},
                                 status=self.history_status, url=url)
        return fake_response(self.changesets[int(parts[-1].split('.')[0])], url=url)

    @property
    def history_gets(self):
        return [url for url in self.gets if url.endswith('/history.json')]


@override_settings(OVERPASS_URL=FAKE_OVERPASS, OSM_API_BASE=API_BASE)
class CreateActionTests(TestCase):

    def setUp(self):
        cache.clear()
        self.event = make_event()
        self.team = Team.objects.create(event=self.event, name='Hydrant Hunters')
        TeamMembership.objects.create(team=self.team, user_identifier='device-1',
                                      display_name='Alice', osm_username='Mapper_Alice')
        self.quest = Quest.objects.create(
            event=self.event, title='Emergency ready', description='Map hydrants and AEDs',
            criteria_type='osm_tags', points_reward=35,
            validation_rules={'required_tags': {'emergency': 'fire_hydrant|defibrillator'},
                              'action': 'create', 'target_count': 3},
        )

    def run_harvest(self, apis, dry_run=False):
        with patch('requests.post', side_effect=apis.post), patch('requests.get', side_effect=apis.get):
            return harvest_event_submissions(self.event.id, dry_run=dry_run)

    def test_version_one_element_is_credited_without_a_history_call(self):
        apis = FakeOsm([NEW_HYDRANT])
        stats = self.run_harvest(apis)

        self.assertEqual(apis.history_gets, [])
        self.assertEqual(stats['osm']['history_lookups'], 0)
        self.assertEqual(stats['osm']['created'], 1)
        sub = Submission.objects.get(platform='osm')
        self.assertEqual(sub.external_id, f'6001/q{self.quest.id}')
        self.assertEqual(sub.author_username, 'mapper_alice')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 18, 2, tzinfo=timezone.utc))
        self.assertEqual(sub.diff_payload['elements'][0]['current_version'], 1)

        row = TrackedOsmElement.objects.get(quest=self.quest, element_type='node', element_id=2001)
        self.assertEqual((row.last_seen_version, row.creator_username, row.creation_changeset),
                         (1, 'mapper_alice', 6001))

    def test_edited_element_is_credited_to_its_creator_via_history(self):
        apis = FakeOsm([EDITED_AED])
        stats = self.run_harvest(apis)

        self.assertEqual(apis.history_gets, [f'{API_BASE}/node/2002/history.json'])
        self.assertEqual(stats['osm']['history_lookups'], 1)
        # Only the creation changeset is looked up, not the one that last touched the element
        self.assertNotIn(f'{API_BASE}/changeset/7002.json', apis.gets)
        sub = Submission.objects.get(platform='osm')
        self.assertEqual(sub.external_id, f'6001/q{self.quest.id}')
        self.assertEqual(sub.author_username, 'mapper_alice')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.element_count, 1)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 18, 3, tzinfo=timezone.utc))
        element = sub.diff_payload['elements'][0]
        self.assertEqual((element['version'], element['current_version'], element['user'], element['timestamp']),
                         (1, 3, 'mapper_alice', '2026-11-03T18:03:00Z'))

        row = TrackedOsmElement.objects.get(quest=self.quest, element_id=2002)
        self.assertEqual(row.last_seen_version, 3)
        self.assertEqual(row.last_editor_username, 'somebody')
        self.assertEqual(row.creator_username, 'mapper_alice')
        self.assertEqual(row.creation_changeset, 6001)
        self.assertEqual(row.created_at_osm, datetime(2026, 11, 3, 18, 3, tzinfo=timezone.utc))

    def test_elements_are_grouped_by_creation_changeset(self):
        stats = self.run_harvest(FakeOsm([NEW_HYDRANT, EDITED_AED]))
        self.assertEqual(stats['osm']['created'], 1)
        sub = Submission.objects.get(platform='osm')
        self.assertEqual(sub.element_count, 2)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 18, 3, tzinfo=timezone.utc))

    def test_history_is_only_fetched_again_when_the_version_goes_up(self):
        self.run_harvest(FakeOsm([EDITED_AED]))

        # Same version on the next run: the stored creation info is reused
        apis = FakeOsm([EDITED_AED])
        stats = self.run_harvest(apis)
        self.assertEqual(apis.history_gets, [])
        self.assertEqual(stats['osm']['history_lookups'], 0)
        self.assertEqual(stats['osm']['harvested'], 1)
        self.assertEqual(stats['osm']['errors'], 0)

        # Someone edits it again: one lookup, and the row follows the new version
        edited_again = dict(EDITED_AED, version=4, user='another_mapper', changeset=7010,
                            timestamp='2026-11-04T11:00:00Z')
        apis = FakeOsm([edited_again])
        stats = self.run_harvest(apis)
        self.assertEqual(apis.history_gets, [f'{API_BASE}/node/2002/history.json'])
        self.assertEqual(stats['osm']['history_lookups'], 1)
        row = TrackedOsmElement.objects.get(quest=self.quest, element_id=2002)
        self.assertEqual((row.last_seen_version, row.last_editor_username), (4, 'another_mapper'))
        self.assertEqual(Submission.objects.get(platform='osm').author_username, 'mapper_alice')

    def test_element_created_before_the_window_is_not_credited(self):
        apis = FakeOsm([OLD_HYDRANT])
        stats = self.run_harvest(apis)

        self.assertEqual(stats['osm']['history_lookups'], 1)
        self.assertEqual(stats['osm']['created'], 0)
        self.assertFalse(Submission.objects.exists())
        row = TrackedOsmElement.objects.get(quest=self.quest, element_id=2003)
        self.assertEqual(row.created_at_osm, datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))

    def test_require_hashtag_is_checked_on_the_creation_changeset(self):
        # Created in an untagged changeset, last edited in a hashtagged one
        histories = {('node', 2002): [dict(HISTORIES[('node', 2002)][0], changeset=6100)]}
        changesets = dict(CHANGESETS)
        changesets[6100] = changeset_payload(6100, 'mapper_alice', '2026-11-03T18:01:00Z',
                                             {'comment': 'Added an AED'}, closed_at='2026-11-03T18:04:00Z')
        changesets[7002] = changeset_payload(7002, 'somebody', '2026-11-04T09:59:00Z', HASHTAGGED,
                                             closed_at='2026-11-04T10:01:00Z')

        stats = self.run_harvest(FakeOsm([EDITED_AED], histories, changesets))
        self.assertEqual(stats['osm']['created'], 0)

        self.quest.validation_rules['require_hashtag'] = False
        self.quest.save()
        stats = self.run_harvest(FakeOsm([EDITED_AED], histories, changesets))
        self.assertEqual(stats['osm']['created'], 1)
        sub = Submission.objects.get(platform='osm')
        self.assertEqual((sub.external_id, sub.author_username), (f'6100/q{self.quest.id}', 'mapper_alice'))

    def test_dry_run_fetches_history_but_writes_no_tracked_rows(self):
        apis = FakeOsm([NEW_HYDRANT, EDITED_AED])
        stats = self.run_harvest(apis, dry_run=True)

        self.assertEqual(len(apis.history_gets), 1)
        self.assertEqual(stats['osm']['history_lookups'], 1)
        self.assertFalse(TrackedOsmElement.objects.exists())
        self.assertFalse(Submission.objects.exists())
        self.assertEqual(stats['would_submit'], [{
            'platform': 'osm', 'external_id': f'6001/q{self.quest.id}', 'author': 'mapper_alice',
            'element_count': 2, 'quest': self.quest.id, 'team': self.team.id, 'action': 'create',
        }])

    def test_history_failure_is_counted_and_retried_next_run(self):
        with self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = self.run_harvest(FakeOsm([EDITED_AED], history_status=503))
        self.assertEqual(stats['osm']['errors'], 1)
        self.assertNotIn('osm.invalid', '\n'.join(logs.output))
        self.assertFalse(TrackedOsmElement.objects.exists())

        apis = FakeOsm([EDITED_AED])
        stats = self.run_harvest(apis)
        self.assertEqual(len(apis.history_gets), 1)
        self.assertEqual(stats['osm']['created'], 1)

    def test_modify_ignores_version_one_elements(self):
        self.quest.validation_rules['action'] = 'modify'
        self.quest.save()
        updated = dict(EDITED_AED, user='mapper_alice', changeset=6001)
        apis = FakeOsm([NEW_HYDRANT, updated])
        stats = self.run_harvest(apis)

        self.assertEqual(apis.history_gets, [])
        self.assertEqual(stats['osm']['created'], 1)
        sub = Submission.objects.get(platform='osm')
        self.assertEqual(sub.element_count, 1)
        self.assertEqual([e['id'] for e in sub.diff_payload['elements']], [2002])
        self.assertFalse(TrackedOsmElement.objects.exists())

    def test_any_is_the_default_and_unknown_actions_fall_back_to_it(self):
        self.quest.validation_rules['action'] = 'delete'
        self.quest.save()
        apis = FakeOsm([NEW_HYDRANT, OLD_HYDRANT])
        stats = self.run_harvest(apis)

        self.assertEqual(apis.history_gets, [])
        self.assertEqual(Submission.objects.get(platform='osm').element_count, 2)
        self.assertEqual(stats['osm']['history_lookups'], 0)
