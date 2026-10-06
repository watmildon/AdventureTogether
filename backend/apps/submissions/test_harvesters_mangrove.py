"""
Tests for the Mangrove Reviews harvester (mangrove_review quests). No network: requests.get is
patched with payloads shaped like https://api.mangrove.reviews/geo responses.
"""

import base64
import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase, override_settings

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.submissions.services.mangrove_harvester import (
    decode_jwt_payload,
    review_external_id,
    subject_coordinates,
)
from apps.submissions.services.tag_matcher import match_author_to_team
from apps.teams.models import Team, TeamMembership

IN_WINDOW = int(datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc).timestamp())
BEFORE_EVENT = int(datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).timestamp())
KID = '-----BEGIN PUBLIC KEY-----MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEexample-----END PUBLIC KEY-----'


def b64url(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip('=')


def review(signature, lat, lon, opinion, iat=IN_WINDOW, nickname='Ada', rating=80,
           include_payload=True, kid=KID):
    metadata = {'client_id': 'https://mangrove.reviews'}
    if nickname:
        metadata['nickname'] = nickname
    payload = {'sub': f'geo:{lat},{lon}?q=Caf%C3%A9%20Example&u=30', 'rating': rating,
               'opinion': opinion, 'iat': iat, 'metadata': metadata}
    item = {
        'signature': signature,
        'jwt': f"{b64url({'alg': 'ES256', 'typ': 'JWT'})}.{b64url(payload)}.c2lnbmF0dXJl",
        'kid': kid,
        'scheme': 'geo',
        'geo': {'coordinates': {'lat': lat, 'lon': lon}, 'uncertainty': 30},
    }
    if include_payload:
        item['payload'] = payload
    return item


GOOD = 'A' * 86
REVIEWS = {'reviews': [
    # Inside the venue polygon, in window, hashtag, long enough -> counts.
    review(GOOD, 38.5800, -121.4920, 'Great tacos and a friendly crew, will be back. #FOSS4GNA2026'),
    # No payload: read from the JWT. Inside, in window, hashtag -> counts.
    review('B' * 86, 38.5790, -121.4930, 'Lovely coffee, quiet tables, fast wifi too. #foss4gna2026',
           nickname='', include_payload=False),
    # Outside the polygon but inside the event perimeter.
    review('C' * 86, 38.5880, -121.5050, 'Outside the cluster but nice anyway. #FOSS4GNA2026'),
    # Before the event.
    review('D' * 86, 38.5800, -121.4920, 'Visited last month, solid lunch spot. #FOSS4GNA2026', iat=BEFORE_EVENT),
    # No hashtag.
    review('E' * 86, 38.5800, -121.4920, 'Great tacos and a friendly crew, will be back soon.'),
    # Hashtag but too short.
    review('F' * 86, 38.5800, -121.4920, 'Yum #FOSS4GNA2026'),
]}


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


@override_settings(MANGROVE_API='https://mangrove.invalid')
class MangroveHarvesterTests(TestCase):

    def setUp(self):
        self.event = Event.objects.create(
            title='Hunt', hashtag='FOSS4GNA2026',
            bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
            start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        self.team = Team.objects.create(event=self.event, name='Reviewers')
        TeamMembership.objects.create(team=self.team, user_identifier='d1', display_name='Ada',
                                      osm_username='someone_else')
        self.quest = Quest.objects.create(
            event=self.event, title='Rate it on Mangrove', description='x', criteria_type='mangrove_review',
            target_geometry=Polygon.from_bbox((-121.496, 38.5775, -121.488, 38.5825)),
            validation_rules={'target_count': 2, 'require_hashtag': True, 'min_opinion_chars': 40},
        )

    def harvest(self, payload=REVIEWS, dry_run=False):
        with patch('requests.get', return_value=ok(payload)) as get:
            stats = harvest_event_submissions(self.event.id, dry_run=dry_run)
        return stats, get

    def test_request_is_one_bbox_query_of_the_quest_area(self):
        _, get = self.harvest()
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], 'https://mangrove.invalid/geo')
        params = get.call_args.kwargs['params']
        self.assertEqual((params['xmin'], params['ymin'], params['xmax'], params['ymax']),
                         ('-121.496000', '38.577500', '-121.488000', '38.582500'))
        self.assertEqual(get.call_args.kwargs['timeout'], 30)
        self.assertIn('AdventureTogether', get.call_args.kwargs['headers']['User-Agent'])

    def test_only_reviews_inside_area_window_with_hashtag_and_length_count(self):
        stats, _ = self.harvest()
        self.assertEqual(stats['mangrove']['created'], 2)
        self.assertEqual(stats['mangrove']['errors'], 0)
        self.assertEqual(
            set(Submission.objects.values_list('external_id', flat=True)),
            {f'{GOOD}/q{self.quest.id}', f"{'B' * 86}/q{self.quest.id}"},
        )

    def test_submission_fields_and_nickname_team_match(self):
        self.harvest()
        sub = Submission.objects.get(external_id=f'{GOOD}/q{self.quest.id}')
        self.assertEqual(sub.platform, 'mangrove')
        self.assertEqual(sub.author_username, 'Ada')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.external_url, f'https://mangrove.reviews/list?signature={GOOD}')
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc))
        self.assertEqual(sub.element_count, 1)
        payload = sub.diff_payload
        self.assertEqual(payload['rating'], 80)
        self.assertEqual(payload['text'], payload['opinion'])
        self.assertEqual(payload['place'], 'Café Example')
        self.assertEqual((payload['lat'], payload['lon']), (38.58, -121.492))
        self.assertEqual(payload['client_id'], 'https://mangrove.reviews')

    def test_jwt_payload_and_anonymous_author(self):
        self.harvest()
        sub = Submission.objects.get(external_id=f"{'B' * 86}/q{self.quest.id}")
        expected = 'anonymous key ' + hashlib.sha256(KID.encode()).hexdigest()[:12]
        self.assertEqual(sub.author_username, expected)
        self.assertIsNone(sub.team)
        self.assertIn('fast wifi', sub.diff_payload['opinion'])

    def test_hashtag_and_length_rules_can_be_relaxed(self):
        self.quest.validation_rules = {'target_count': 2, 'require_hashtag': False}
        self.quest.save()
        stats, _ = self.harvest()
        # Adds the no-hashtag review and the short one; the outside and early ones still fail.
        self.assertEqual(stats['mangrove']['created'], 4)

    def test_min_rating(self):
        payload = {'reviews': [
            review('G' * 86, 38.58, -121.492, 'Cold food, slow service, sticky tables. #FOSS4GNA2026', rating=20),
        ]}
        self.quest.validation_rules = {'min_rating': 60}
        self.quest.save()
        stats, _ = self.harvest(payload)
        self.assertEqual(stats['mangrove']['created'], 0)
        self.quest.validation_rules = {}
        self.quest.save()
        stats, _ = self.harvest(payload)
        self.assertEqual(stats['mangrove']['created'], 1)

    def test_whole_perimeter_quest_and_rerun_is_idempotent(self):
        self.quest.target_geometry = None
        self.quest.save()
        stats, get = self.harvest()
        self.assertEqual(get.call_args.kwargs['params']['xmin'], '-121.509000')
        self.assertEqual(stats['mangrove']['created'], 3)  # the outside-the-cluster review now counts
        stats, _ = self.harvest()
        self.assertEqual(stats['mangrove']['created'], 0)
        self.assertEqual(stats['mangrove']['harvested'], 3)

    def test_point_target_uses_radius(self):
        self.quest.target_geometry = Point(-121.4920, 38.5800, srid=4326)
        self.quest.validation_rules = {'radius_m': 50, 'require_hashtag': True}
        self.quest.save()
        stats, get = self.harvest()
        params = get.call_args.kwargs['params']
        self.assertLess(float(params['xmin']), -121.4920)
        self.assertGreater(float(params['xmax']), -121.4920)
        self.assertEqual(stats['mangrove']['created'], 2)  # GOOD and the short one; B is ~140 m away

    def test_failure_is_counted_without_url(self):
        resp = MagicMock()
        resp.status_code = 503
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError('503 for url: https://mangrove.invalid/geo')
        with patch('requests.get', return_value=resp), self.assertLogs('apps.submissions.harvest') as logs:
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['mangrove']['errors'], 1)
        self.assertNotIn('mangrove.invalid', '\n'.join(logs.output))

    def test_dry_run_writes_nothing(self):
        stats, _ = self.harvest(dry_run=True)
        self.assertEqual(len(stats['would_submit']), 2)
        self.assertFalse(Submission.objects.exists())


class MangroveHelperTests(TestCase):

    def test_decode_jwt_payload(self):
        token = f"{b64url({'alg': 'ES256'})}.{b64url({'sub': 'geo:1,2', 'iat': 5})}.sig"
        self.assertEqual(decode_jwt_payload(token), {'sub': 'geo:1,2', 'iat': 5})
        self.assertEqual(decode_jwt_payload('not-a-jwt'), {})
        self.assertEqual(decode_jwt_payload('a.!!!.b'), {})
        self.assertEqual(decode_jwt_payload(None), {})

    def test_subject_coordinates(self):
        self.assertEqual(subject_coordinates('geo:38.579,-121.49?q=Name&u=30', {}), (38.579, -121.49))
        self.assertEqual(subject_coordinates('https://example.org', {'geo': {'coordinates': {'lat': 1, 'lon': 2}}}),
                         (1.0, 2.0))
        self.assertEqual(subject_coordinates('https://example.org', {}), (None, None))

    def test_external_id_keeps_signature_or_hashes_a_long_one(self):
        self.assertEqual(review_external_id('abc', 7), 'abc/q7')
        long_sig = 'x' * 300
        eid = review_external_id(long_sig, 7)
        self.assertLessEqual(len(eid), 255)
        self.assertTrue(eid.endswith('/q7'))
        self.assertNotEqual(eid, review_external_id('y' * 300, 7))


class MangroveTeamMatchTests(TestCase):

    def test_display_name_is_tried_before_user_identifier(self):
        event = Event.objects.create(
            title='Hunt', hashtag='X', bounding_polygon=Polygon.from_bbox((0, 0, 1, 1)),
            start_time=datetime(2026, 11, 2, tzinfo=timezone.utc), end_time=datetime(2026, 11, 3, tzinfo=timezone.utc),
        )
        by_name = Team.objects.create(event=event, name='By name')
        by_id = Team.objects.create(event=event, name='By id')
        TeamMembership.objects.create(team=by_id, user_identifier='ada', display_name='Someone')
        TeamMembership.objects.create(team=by_name, user_identifier='u2', display_name='ADA')
        self.assertEqual(match_author_to_team(event, 'ada', platform='mangrove'), by_name)
        # Other platforms keep user_identifier first.
        self.assertEqual(match_author_to_team(event, 'ada', platform='github'), by_id)
        self.assertEqual(match_author_to_team(event, 'u2', platform='mangrove'), by_name)
