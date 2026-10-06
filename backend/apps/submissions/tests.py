"""
Unit and Integration Tests for Multi-Platform Ingestion, Diff Parsing, and Host Verification.
"""

from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from django.contrib.gis.geos import Polygon
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.events.models import Event
from apps.quests.models import Quest
from apps.teams.models import Team, TeamMembership
from apps.submissions.models import QuestProgress, Submission
from apps.submissions.serializers import SubmissionSerializer
from apps.submissions.services.progress import (
    mark_verified,
    recompute_quest_progress,
    set_submission_verification,
)
from apps.submissions.services.osm_harvester import parse_osm_changeset_xml, parse_osm_change_diff
from apps.submissions.services.wikimedia_harvester import parse_wikimedia_search_response
from apps.submissions.services.wikidata_harvester import parse_wikidata_search_response
from apps.submissions.services.harvest_worker import harvest_event_submissions


SAMPLE_OSM_CHANGESETS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
  <changeset id="1456789" user="mapper_alice" created_at="2026-10-04T12:00:00Z" min_lat="37.76" min_lon="-122.43" max_lat="37.78" max_lon="-122.41">
    <tag k="comment" v="Added restaurant hours for #SFMapHunt2026"/>
    <tag k="created_by" v="StreetComplete 55.0"/>
  </changeset>
  <changeset id="9999999" user="unrelated_user" created_at="2026-10-04T12:05:00Z">
    <tag k="comment" v="Unrelated edit"/>
  </changeset>
</osm>
"""

SAMPLE_OSM_CHANGE_DIFF_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osmChange version="0.6">
  <modify>
    <node id="54321" lat="37.7749" lon="-122.4194" version="3">
      <tag k="amenity" v="restaurant"/>
      <tag k="name" v="Bistro Central"/>
      <tag k="opening_hours" v="Mo-Fr 11:00-21:00"/>
    </node>
  </modify>
</osmChange>
"""


class SubmissionHarvesterParserTests(TestCase):
    """
    Validates XML and JSON parsers for OSM, Wikimedia Commons, and Wikidata.
    """

    def test_parse_osm_changeset_xml(self):
        """Parses OSM changesets and filters matching hashtag."""
        items = parse_osm_changeset_xml(SAMPLE_OSM_CHANGESETS_XML, "SFMapHunt2026")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['external_id'], '1456789')
        self.assertEqual(items[0]['author_username'], 'mapper_alice')
        self.assertIn('SFMapHunt2026', items[0]['comment'])

    def test_parse_osm_change_diff(self):
        """Parses osmChange XML and extracts modified element tags and coordinates."""
        diff = parse_osm_change_diff(SAMPLE_OSM_CHANGE_DIFF_XML)
        self.assertEqual(diff['elements_summary']['modified'], 1)
        self.assertEqual(len(diff['modified_tags_list']), 1)
        self.assertEqual(diff['modified_tags_list'][0]['opening_hours'], 'Mo-Fr 11:00-21:00')
        self.assertEqual(diff['actions'][0]['id'], '54321')

    def test_parse_wikimedia_search_response(self):
        """Parses MediaWiki JSON search response into submission items."""
        mock_data = {
            'query': {
                'search': [{
                    'pageid': 888123,
                    'title': 'File:SF Mural Mission.jpg',
                    'snippet': 'Uploaded for #SFMapHunt2026',
                    'timestamp': '2026-10-04T12:30:00Z'
                }]
            }
        }
        items = parse_wikimedia_search_response(mock_data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['external_id'], '888123')
        self.assertEqual(items[0]['platform'], 'commons')
        self.assertIn('SF_Mural_Mission.jpg', items[0]['external_url'])

    def test_parse_wikidata_search_response(self):
        """Parses Wikidata JSON search response into submission items."""
        mock_data = {
            'query': {
                'search': [{
                    'pageid': 999456,
                    'title': 'Q424242',
                    'snippet': 'Added image statement #SFMapHunt2026',
                    'timestamp': '2026-10-04T12:45:00Z'
                }]
            }
        }
        items = parse_wikidata_search_response(mock_data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['external_id'], '999456')
        self.assertEqual(items[0]['platform'], 'wikidata')


class SubmissionWorkflowAPITests(TestCase):
    """
    Validates end-to-end harvest staging, quest matching, and host verification approval.
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
            title="San Francisco Landmark Hunt",
            hashtag="SFMapHunt2026",
            bounding_polygon=self.sf_polygon,
            start_time=now,
            end_time=now + timedelta(hours=6),
        )
        self.team = Team.objects.create(
            event=self.event,
            name="Alpha Explorers",
            join_code="ALPHAX",
            score=0
        )
        self.membership = TeamMembership.objects.create(
            team=self.team,
            user_identifier="mapper_alice",
            display_name="Alice"
        )
        self.quest = Quest.objects.create(
            event=self.event,
            title="Map Restaurant Opening Hours",
            description="Add opening_hours to restaurants.",
            criteria_type="osm_tags",
            validation_rules={
                "required_tags": {
                    "amenity": "restaurant",
                    "opening_hours": "*"
                }
            },
            points_reward=25
        )

    @patch('apps.submissions.services.harvest_worker.fetch_osm_changesets')
    @patch('apps.submissions.services.harvest_worker.fetch_osm_changeset_diff')
    def test_harvest_event_submissions_creates_and_matches(self, mock_diff, mock_changesets):
        """Harvesting creates a Submission, extracts diff, and links Quest and Team."""
        mock_changesets.return_value = [{
            'external_id': '1456789',
            'platform': 'osm',
            'author_username': 'mapper_alice',
            'external_url': 'https://www.openstreetmap.org/changeset/1456789',
            'comment': 'Mapped hours for #SFMapHunt2026'
        }]
        mock_diff.return_value = {
            'elements_summary': {'modified': 1},
            'modified_tags_list': [{'amenity': 'restaurant', 'opening_hours': '11:00-22:00'}]
        }

        stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['created'], 1)
        self.assertEqual(stats['matched'], 1)

        submission = Submission.objects.get(external_id='1456789')
        self.assertEqual(submission.quest, self.quest)
        self.assertEqual(submission.team, self.team)
        self.assertFalse(submission.is_verified)

    def test_host_verify_submission_awards_points(self):
        """Host verifying a submission sets is_verified=True and increments team score."""
        submission = Submission.objects.create(
            event=self.event,
            quest=self.quest,
            team=self.team,
            platform='osm',
            external_id='987654',
            author_username='mapper_alice',
            external_url='https://www.openstreetmap.org/changeset/987654',
            diff_payload={'tags': {'opening_hours': '10-22'}},
            is_verified=False
        )

        url = reverse('submissions:submission-verify', kwargs={'pk': submission.id})
        data = {
            'is_verified': True,
            'verified_by_username': 'HostMaster'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        submission.refresh_from_db()
        self.assertTrue(submission.is_verified)
        self.assertEqual(submission.verified_by_username, 'HostMaster')
        self.assertIsNotNone(submission.verified_at)

        # Team score should be incremented by 25
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 25)

    def test_verify_twice_then_revoke(self):
        """Re-verifying does not double-award; un-verifying revokes the points."""
        submission = Submission.objects.create(
            event=self.event, quest=self.quest, team=self.team, platform='osm',
            external_id='111', author_username='mapper_alice',
            external_url='https://www.openstreetmap.org/changeset/111',
        )
        url = reverse('submissions:submission-verify', kwargs={'pk': submission.id})
        self.client.post(url, {'is_verified': True}, format='json')
        self.client.post(url, {'is_verified': True}, format='json')
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 25)

        response = self.client.post(url, {'is_verified': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_verified'])
        self.assertIsNone(response.data['verified_by_username'])
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)


class QuestProgressServiceTests(TestCase):
    """
    Validates recompute_quest_progress: counted quests, awarding once, and revoking.
    """

    def setUp(self):
        polygon = Polygon([
            (-121.51, 38.57), (-121.48, 38.57), (-121.48, 38.59), (-121.51, 38.59), (-121.51, 38.57),
        ])
        now = datetime.now(timezone.utc)
        self.event = Event.objects.create(
            title="Progress Hunt", hashtag="ProgressHunt", bounding_polygon=polygon,
            start_time=now, end_time=now + timedelta(days=1),
        )
        self.team = Team.objects.create(event=self.event, name="Counters", join_code="COUNT1", score=0)
        self.counted_quest = Quest.objects.create(
            event=self.event, title="Hours for 5 cafes", description="d",
            validation_rules={"required_tags": {"amenity": "cafe", "opening_hours": "*"}, "target_count": 5},
            points_reward=40,
        )
        self._next_id = 1

    def make_submission(self, quest=None, element_count=1, is_verified=False, platform='osm'):
        self._next_id += 1
        return Submission.objects.create(
            event=self.event, quest=quest or self.counted_quest, team=self.team,
            platform=platform, external_id=str(self._next_id), author_username='mapper',
            external_url=f'https://www.openstreetmap.org/changeset/{self._next_id}',
            element_count=element_count, is_verified=is_verified,
        )

    def test_counted_quest_awards_only_when_target_reached(self):
        first = self.make_submission(element_count=3)
        set_submission_verification(first, True, 'Host')
        progress = QuestProgress.objects.get(team=self.team, quest=self.counted_quest)
        self.assertEqual(progress.count, 3)
        self.assertIsNone(progress.completed_at)
        self.assertFalse(progress.points_awarded)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)

        second = self.make_submission(element_count=2)
        set_submission_verification(second, True, 'Host')
        progress.refresh_from_db()
        self.assertEqual(progress.count, 5)
        self.assertIsNotNone(progress.completed_at)
        self.assertTrue(progress.points_awarded)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 40)

    def test_extra_contributions_do_not_award_twice(self):
        set_submission_verification(self.make_submission(element_count=5), True)
        set_submission_verification(self.make_submission(element_count=2), True)
        recompute_quest_progress(self.team, self.counted_quest)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 40)
        self.assertEqual(QuestProgress.objects.get(team=self.team).count, 7)

    def test_unverified_submissions_do_not_count(self):
        self.make_submission(element_count=10, is_verified=False)
        progress = recompute_quest_progress(self.team, self.counted_quest)
        self.assertEqual(progress.count, 0)
        self.assertFalse(progress.points_awarded)

    def test_dropping_below_target_revokes_points(self):
        a = self.make_submission(element_count=3)
        b = self.make_submission(element_count=2)
        set_submission_verification(a, True)
        set_submission_verification(b, True)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 40)

        set_submission_verification(b, False)
        progress = QuestProgress.objects.get(team=self.team, quest=self.counted_quest)
        self.assertEqual(progress.count, 3)
        self.assertIsNone(progress.completed_at)
        self.assertFalse(progress.points_awarded)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)

    def test_revoke_floors_score_at_zero(self):
        set_submission_verification(self.make_submission(element_count=5), True)
        Team.objects.filter(pk=self.team.pk).update(score=10)  # e.g. manual host adjustment
        sub = Submission.objects.get(team=self.team)
        set_submission_verification(sub, False)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)

    def test_completed_at_is_kept_on_recompute(self):
        set_submission_verification(self.make_submission(element_count=5), True)
        first_completed = QuestProgress.objects.get(team=self.team).completed_at
        set_submission_verification(self.make_submission(element_count=1), True)
        self.assertEqual(QuestProgress.objects.get(team=self.team).completed_at, first_completed)

    def test_mark_verified_awards_for_auto_verified_submission(self):
        checkin_quest = Quest.objects.create(
            event=self.event, title="Icebreaker", description="d",
            criteria_type="location_checkin", points_reward=10,
        )
        sub = self.make_submission(quest=checkin_quest, platform='checkin')
        mark_verified(sub, by='system')
        sub.refresh_from_db()
        self.assertTrue(sub.is_verified)
        self.assertEqual(sub.verified_by_username, 'system')
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 10)

    def test_submission_without_team_is_ignored(self):
        sub = self.make_submission(element_count=5)
        sub.team = None
        sub.save()
        set_submission_verification(sub, True)
        self.assertFalse(QuestProgress.objects.exists())

    def test_platform_display_for_new_platforms(self):
        sub = self.make_submission(platform='panoramax')
        data = SubmissionSerializer(sub).data
        self.assertEqual(data['platform_display'], 'Panoramax')
        self.assertEqual(data['element_count'], 1)
        self.assertIn('contributed_at', data)
