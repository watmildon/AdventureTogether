"""
Unit and Integration Tests for Team Formation, Join Codes, and Rosters.
"""

from datetime import datetime, timezone, timedelta
from django.contrib.gis.geos import Polygon
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import QuestProgress
from .models import Team, TeamMembership


class TeamManagementAPITests(TestCase):
    """
    Validates team creation, join code mechanics, and participant enrollment.
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
            title="Hayes Valley Hunt",
            description="Explore Hayes Valley with your team.",
            hashtag="HayesHunt",
            bounding_polygon=self.sf_polygon,
            start_time=now,
            end_time=now + timedelta(hours=3),
        )
        self.team = Team.objects.create(
            event=self.event,
            name="Urban Explorers",
            join_code="EXPLORE1"
        )

    def test_create_team_generates_join_code(self):
        """Creating a team automatically assigns a unique join code."""
        url = reverse('teams:team-list')
        data = {
            'event': self.event.id,
            'name': 'Street Cartographers'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(len(response.data.get('join_code')) >= 6)

    def test_join_team_success(self):
        """Participant successfully joins team using join code."""
        url = reverse('teams:team-join')
        data = {
            'join_code': 'EXPLORE1',
            'user_identifier': 'user-device-uuid-1234',
            'display_name': 'Alice the Mapper'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('Successfully joined team', response.data['message'])

        # Verify membership in database
        membership = TeamMembership.objects.get(user_identifier='user-device-uuid-1234')
        self.assertEqual(membership.team, self.team)
        self.assertEqual(membership.display_name, 'Alice the Mapper')

    def test_join_team_invalid_code(self):
        """Joining with invalid code returns 404."""
        url = reverse('teams:team-join')
        data = {
            'join_code': 'NONEXISTENT',
            'user_identifier': 'user-device-uuid-999',
            'display_name': 'Bob'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TeamUsernamesAndProgressAPITests(TestCase):
    """
    Validates contributor usernames on join and the per-team quest progress endpoint.
    """

    def setUp(self):
        self.client = APIClient()
        polygon = Polygon([
            (-121.51, 38.57), (-121.48, 38.57), (-121.48, 38.59), (-121.51, 38.59), (-121.51, 38.57),
        ])
        now = datetime.now(timezone.utc)
        self.event = Event.objects.create(
            title="FOSS4G NA 2026", hashtag="FOSS4GNA2026", bounding_polygon=polygon,
            start_time=now, end_time=now + timedelta(days=3),
        )
        self.team = Team.objects.create(event=self.event, name="Mappers", join_code="MAPPER")

    def test_join_with_platform_usernames(self):
        response = self.client.post(reverse('teams:team-join'), {
            'join_code': 'MAPPER',
            'user_identifier': 'device-1',
            'display_name': 'Alice',
            'osm_username': 'alice_osm',
            'wikimedia_username': 'Alice (WMF)',
            'github_username': '@alice-gh',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        member = response.data['membership']
        self.assertEqual(member['osm_username'], 'alice_osm')
        self.assertEqual(member['wikimedia_username'], 'Alice (WMF)')
        self.assertEqual(member['github_username'], 'alice-gh')  # leading @ stripped
        # The roster embedded in the team also exposes them.
        self.assertEqual(response.data['team']['memberships'][0]['osm_username'], 'alice_osm')

    def test_rejoin_without_usernames_keeps_existing_values(self):
        url = reverse('teams:team-join')
        self.client.post(url, {
            'join_code': 'MAPPER', 'user_identifier': 'device-1', 'osm_username': 'alice_osm',
        }, format='json')
        response = self.client.post(url, {
            'join_code': 'MAPPER', 'user_identifier': 'device-1', 'display_name': 'Alice again',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership = TeamMembership.objects.get(user_identifier='device-1')
        self.assertEqual(membership.osm_username, 'alice_osm')
        self.assertEqual(membership.display_name, 'Alice again')

    def test_rejoin_with_blank_username_clears_it(self):
        url = reverse('teams:team-join')
        self.client.post(url, {
            'join_code': 'MAPPER', 'user_identifier': 'device-1', 'github_username': 'alice-gh',
        }, format='json')
        self.client.post(url, {
            'join_code': 'MAPPER', 'user_identifier': 'device-1', 'github_username': '',
        }, format='json')
        self.assertEqual(TeamMembership.objects.get(user_identifier='device-1').github_username, '')

    def test_join_without_usernames_defaults_to_blank(self):
        response = self.client.post(reverse('teams:team-join'), {
            'join_code': 'MAPPER', 'user_identifier': 'device-2',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['membership']['osm_username'], '')

    def test_progress_lists_every_quest_including_unstarted(self):
        trees = Quest.objects.create(
            event=self.event, title="Shade the grid", description="d",
            validation_rules={"target_count": 10}, points_reward=40,
        )
        checkin = Quest.objects.create(
            event=self.event, title="Icebreaker check-in", description="d",
            criteria_type="location_checkin", points_reward=10,
        )
        completed = datetime.now(timezone.utc)
        QuestProgress.objects.create(
            team=self.team, quest=checkin, count=1, completed_at=completed, points_awarded=True,
        )
        # Progress belonging to another team must not leak in.
        other = Team.objects.create(event=self.event, name="Others", join_code="OTHERS")
        QuestProgress.objects.create(team=other, quest=trees, count=7)

        response = self.client.get(reverse('teams:team-progress', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {row['quest']: row for row in response.data}
        self.assertEqual(set(rows), {trees.id, checkin.id})

        self.assertEqual(rows[trees.id]['quest_title'], "Shade the grid")
        self.assertEqual(rows[trees.id]['count'], 0)
        self.assertEqual(rows[trees.id]['target_count'], 10)
        self.assertIsNone(rows[trees.id]['completed_at'])
        self.assertFalse(rows[trees.id]['points_awarded'])

        self.assertEqual(rows[checkin.id]['count'], 1)
        self.assertEqual(rows[checkin.id]['target_count'], 1)
        self.assertIsNotNone(rows[checkin.id]['completed_at'])
        self.assertTrue(rows[checkin.id]['points_awarded'])

        # Listing progress must not create placeholder rows.
        self.assertEqual(QuestProgress.objects.filter(team=self.team).count(), 1)
