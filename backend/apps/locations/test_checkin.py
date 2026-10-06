"""
Tests for GPS check-in quests (criteria_type 'location_checkin').
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.gis.geos import Point, Polygon
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import QuestProgress, Submission
from apps.submissions.services.checkin import participant_checkins, process_checkin_ping
from apps.submissions.services.progress import set_submission_verification
from apps.teams.models import Team, TeamMembership
from .geo import haversine_m
from .models import LocationPing

# Sacramento Public Market entrance, roughly.
TARGET_LON, TARGET_LAT = -121.4944, 38.5800
# ~1.11 m per 0.00001 deg latitude.
NEAR = (TARGET_LON, TARGET_LAT + 0.0002)    # ~22 m north
FAR = (TARGET_LON, TARGET_LAT + 0.0020)     # ~222 m north
T0 = datetime(2026, 11, 2, 18, 30, tzinfo=dt_timezone.utc)


class HaversineTests(TestCase):
    def test_known_distance(self):
        # One degree of latitude is ~111.2 km.
        self.assertAlmostEqual(haversine_m(0, 0, 1, 0), 111_195, delta=50)
        self.assertEqual(haversine_m(TARGET_LAT, TARGET_LON, TARGET_LAT, TARGET_LON), 0)


class CheckinQuestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        perimeter = Polygon([
            (-121.51, 38.57), (-121.48, 38.57), (-121.48, 38.59), (-121.51, 38.59), (-121.51, 38.57),
        ])
        self.event = Event.objects.create(
            title="Check-in Hunt", hashtag="CheckinHunt", bounding_polygon=perimeter,
            start_time=T0 - timedelta(days=1), end_time=T0 + timedelta(days=3),
        )
        self.team = Team.objects.create(event=self.event, name="Alpha", join_code="ALPHA9")
        TeamMembership.objects.create(team=self.team, user_identifier="alice", display_name="Alice")
        self.quest = self.make_quest()
        self.ping_url = reverse('locations:location-ping')
        self.checkins_url = reverse('locations:location-checkins')

    def make_quest(self, **kwargs):
        defaults = dict(
            event=self.event, title="Icebreaker check-in", description="Be there.",
            criteria_type='location_checkin', target_geometry=Point(TARGET_LON, TARGET_LAT, srid=4326),
            validation_rules={'radius_m': 50}, points_reward=10,
        )
        defaults.update(kwargs)
        return Quest.objects.create(**defaults)

    def ping(self, at, where=NEAR, user="alice", name="Alice"):
        with mock.patch('django.utils.timezone.now', return_value=at):
            response = self.client.post(self.ping_url, {
                'event': self.event.id, 'user_identifier': user, 'display_name': name,
                'longitude': where[0], 'latitude': where[1],
            }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def submission(self, user="alice", quest=None):
        quest = quest or self.quest
        return Submission.objects.get(platform='checkin', external_id=f"q{quest.id}/{user}")

    def test_in_range_creates_and_verifies_immediately_and_awards_points(self):
        self.ping(T0)
        sub = self.submission()
        self.assertTrue(sub.is_verified)
        self.assertEqual(sub.verified_by_username, 'system:checkin')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.quest, self.quest)
        self.assertEqual(sub.author_username, "Alice")
        self.assertEqual(sub.element_count, 1)
        self.assertEqual(sub.contributed_at, T0)
        self.assertTrue(sub.external_url.startswith("https://www.openstreetmap.org/#map=19/"))
        self.assertEqual(sub.diff_payload['first_seen'], T0.isoformat())
        self.assertEqual(sub.diff_payload['ping_count'], 1)
        self.assertEqual(sub.diff_payload['radius_m'], 50)
        self.assertLess(sub.diff_payload['distance_m'], 50)
        self.assertIn('auto_verified_at', sub.diff_payload)

        progress = QuestProgress.objects.get(team=self.team, quest=self.quest)
        self.assertTrue(progress.points_awarded)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 10)

        # A second ping updates the same row and does not double-award.
        self.ping(T0 + timedelta(minutes=1))
        self.assertEqual(Submission.objects.filter(platform='checkin').count(), 1)
        self.assertEqual(self.submission().diff_payload['ping_count'], 2)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 10)

    def test_out_of_range_creates_nothing(self):
        response = self.ping(T0, where=FAR)
        self.assertEqual(response.data['checkins'], [])
        self.assertFalse(Submission.objects.filter(platform='checkin').exists())

    def test_quest_without_target_geometry_is_ignored(self):
        self.quest.delete()
        self.make_quest(target_geometry=None)
        self.ping(T0)
        self.assertFalse(Submission.objects.filter(platform='checkin').exists())

    def test_polygon_target_counts_pings_inside_polygon(self):
        self.quest.delete()
        # A 300 m-ish square whose centroid is well over 50 m from FAR, but FAR is inside it.
        square = Polygon([
            (TARGET_LON - 0.002, TARGET_LAT - 0.001), (TARGET_LON + 0.002, TARGET_LAT - 0.001),
            (TARGET_LON + 0.002, TARGET_LAT + 0.003), (TARGET_LON - 0.002, TARGET_LAT + 0.003),
            (TARGET_LON - 0.002, TARGET_LAT - 0.001),
        ], srid=4326)
        quest = self.make_quest(target_geometry=square)
        response = self.ping(T0, where=FAR)
        self.assertEqual(response.data['checkins'][0]['distance_m'], 0.0)
        self.assertTrue(self.submission(quest=quest).is_verified)

    def test_dwell_requires_min_minutes(self):
        self.quest.validation_rules = {'radius_m': 50, 'min_minutes': 5}
        self.quest.save()

        r1 = self.ping(T0)
        self.assertEqual(r1.data['checkins'][0]['status'], 'in_range')
        self.assertFalse(self.submission().is_verified)

        r2 = self.ping(T0 + timedelta(minutes=4, seconds=59))
        self.assertEqual(r2.data['checkins'][0]['status'], 'in_range')
        self.assertFalse(self.submission().is_verified)

        r3 = self.ping(T0 + timedelta(minutes=5))
        self.assertEqual(r3.data['checkins'][0]['status'], 'verified')
        sub = self.submission()
        self.assertTrue(sub.is_verified)
        self.assertEqual(sub.diff_payload['first_seen'], T0.isoformat())
        self.assertEqual(sub.diff_payload['last_seen'], (T0 + timedelta(minutes=5)).isoformat())
        self.assertEqual(sub.diff_payload['ping_count'], 3)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 10)

    def test_dwell_restarts_after_a_long_gap(self):
        self.quest.validation_rules = {'radius_m': 50, 'min_minutes': 5}
        self.quest.save()
        self.ping(T0)
        # Back three hours later: that is not five continuous minutes on site.
        self.ping(T0 + timedelta(hours=3))
        self.assertFalse(self.submission().is_verified)
        self.ping(T0 + timedelta(hours=3, minutes=5))
        sub = self.submission()
        self.assertTrue(sub.is_verified)
        self.assertEqual(sub.diff_payload['first_seen'], T0.isoformat())

    def test_closed_quest_window_is_ignored(self):
        self.quest.window_start = T0 + timedelta(hours=1)
        self.quest.window_end = T0 + timedelta(hours=2)
        self.quest.save()
        response = self.ping(T0)
        self.assertEqual(response.data['checkins'], [])
        self.assertFalse(Submission.objects.filter(platform='checkin').exists())

        self.ping(T0 + timedelta(hours=1, minutes=30))
        self.assertTrue(self.submission().is_verified)

    def test_inactive_quest_is_ignored(self):
        self.quest.is_active = False
        self.quest.save()
        self.ping(T0)
        self.assertFalse(Submission.objects.filter(platform='checkin').exists())

    def test_participant_without_team_gets_evidence_but_no_points(self):
        self.ping(T0, user="loner", name="Loner")
        sub = self.submission(user="loner")
        self.assertIsNone(sub.team)
        self.assertEqual(sub.author_username, "Loner")
        self.assertFalse(QuestProgress.objects.exists())
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)

    def test_late_team_join_credits_existing_checkin(self):
        self.ping(T0, user="bob", name="Bob")
        self.assertIsNone(self.submission(user="bob").team)
        TeamMembership.objects.create(team=self.team, user_identifier="bob", display_name="Bob")
        self.ping(T0 + timedelta(minutes=1), user="bob", name="Bob")
        self.assertEqual(self.submission(user="bob").team, self.team)
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 10)

    def test_host_revocation_is_not_undone_by_later_ping(self):
        self.ping(T0)
        set_submission_verification(self.submission(), False, by='host')
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)

        response = self.ping(T0 + timedelta(minutes=2))
        sub = self.submission()
        self.assertFalse(sub.is_verified)
        self.assertEqual(sub.diff_payload['ping_count'], 2)
        self.assertEqual(response.data['checkins'][0]['status'], 'in_range')
        self.team.refresh_from_db()
        self.assertEqual(self.team.score, 0)

    def test_ping_response_carries_checkins(self):
        other = self.make_quest(title="Far away quest", target_geometry=Point(*FAR, srid=4326))
        response = self.ping(T0)
        self.assertEqual(response.data['user_identifier'], 'alice')
        self.assertEqual(len(response.data['checkins']), 1)
        checkin = response.data['checkins'][0]
        self.assertEqual(checkin['quest'], self.quest.id)
        self.assertNotEqual(checkin['quest'], other.id)
        self.assertEqual(checkin['quest_title'], "Icebreaker check-in")
        self.assertEqual(checkin['status'], 'verified')
        self.assertAlmostEqual(checkin['distance_m'], 22.2, delta=1)

    def test_checkin_failure_does_not_fail_ping(self):
        with mock.patch('apps.locations.views.process_checkin_ping', side_effect=RuntimeError("boom")):
            with self.assertLogs('apps.locations.views', level='ERROR'):
                response = self.ping(T0)
        self.assertEqual(response.data['checkins'], [])
        self.assertEqual(response.data['user_identifier'], 'alice')

    def test_checkins_endpoint(self):
        dwell = self.make_quest(title="Dwell quest", validation_rules={'radius_m': 50, 'min_minutes': 10})
        self.ping(T0)
        self.ping(T0, user="carol", name="Carol")

        response = self.client.get(self.checkins_url, {'event': self.event.id, 'user_identifier': 'alice'})
        self.assertEqual(response.status_code, 200)
        rows = {row['quest']: row for row in response.data}
        self.assertEqual(set(rows), {self.quest.id, dwell.id})
        self.assertEqual(rows[self.quest.id]['status'], 'verified')
        self.assertEqual(rows[self.quest.id]['quest_title'], "Icebreaker check-in")
        self.assertEqual(rows[dwell.id]['status'], 'pending')
        self.assertEqual(rows[dwell.id]['first_seen'], T0.isoformat())
        self.assertEqual(rows[dwell.id]['last_seen'], T0.isoformat())

        set_submission_verification(self.submission(), False, by='host')
        response = self.client.get(self.checkins_url, {'event': self.event.id, 'user_identifier': 'alice'})
        self.assertEqual({r['quest']: r['status'] for r in response.data}[self.quest.id], 'revoked')

        self.assertEqual(self.client.get(self.checkins_url, {'event': self.event.id}).status_code, 400)
        self.assertEqual(
            self.client.get(self.checkins_url, {'event': 'x', 'user_identifier': 'alice'}).status_code, 400
        )
        empty = self.client.get(self.checkins_url, {'event': self.event.id, 'user_identifier': 'nobody'})
        self.assertEqual(empty.data, [])

    def test_checkins_are_ordered_by_last_seen(self):
        far_quest = self.make_quest(title="Far quest", target_geometry=Point(*FAR, srid=4326))
        self.ping(T0)                                # first check-in at the near quest
        self.ping(T0 + timedelta(minutes=1), FAR)    # then the far quest
        self.ping(T0 + timedelta(minutes=5))         # back at the near quest: most recent activity

        ordered = participant_checkins(self.event.id, 'alice')
        self.assertEqual([sub.quest_id for sub in ordered], [self.quest.id, far_quest.id])
        response = self.client.get(self.checkins_url, {'event': self.event.id, 'user_identifier': 'alice'})
        self.assertEqual([row['quest'] for row in response.data], [self.quest.id, far_quest.id])

    def make_ping(self, user, team=None):
        with mock.patch('django.utils.timezone.now', return_value=T0):
            return LocationPing.objects.create(
                event=self.event, user_identifier=user, display_name=user.title(), team=team,
                coordinates=Point(*NEAR, srid=4326),
            )

    def test_team_stored_on_ping_is_used_without_membership_query(self):
        ping = self.make_ping("alice", team=self.team)
        with CaptureQueriesContext(connection) as queries:
            process_checkin_ping(ping)
        self.assertFalse(any('teams_teammembership' in q['sql'] for q in queries.captured_queries))
        self.assertEqual(self.submission().team, self.team)

    def test_ping_without_team_falls_back_to_membership(self):
        process_checkin_ping(self.make_ping("alice"))
        self.assertEqual(self.submission().team, self.team)
