"""
Tests for value-scoring quests (validation_rules.scoring): reading values out of submissions,
per-bucket points, the extreme bonus moving between teams, host corrections, quest deletion,
and the standings endpoint. No network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Polygon
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import QuestProgress, Submission
from apps.submissions.services.harvest_common import HarvestContext, upsert_submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.submissions.services.progress import recompute_quest_progress, set_submission_verification
from apps.submissions.services.value_extraction import apply_extraction, extract_values
from apps.teams.models import Team, TeamMembership

COMMONS_API = 'https://commons.invalid/w/api.php'

STAMP_SCORING = {
    'value': {'source': 'description', 'pattern': r'\b((?:18|19|20)\d{2})\b', 'kind': 'year'},
    'per_bucket': {'size': 10, 'points': 5},
    'extreme_bonus': {'direction': 'min', 'points': 25},
}


def make_event():
    return Event.objects.create(
        title='Hunt', hashtag='FOSS4GNA2026',
        bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
        start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
    )


def make_quest(event, scoring=None, criteria_type='wikimedia_commons', points_reward=10, title='Stamps'):
    rules = {'target_count': 1}
    if scoring is not None:
        rules['scoring'] = scoring
    return Quest.objects.create(event=event, title=title, description='d', criteria_type=criteria_type,
                                validation_rules=rules, points_reward=points_reward)


class ValueExtractionTests(TestCase):

    def setUp(self):
        self.event = make_event()

    def test_year_from_description_strips_html(self):
        quest = make_quest(self.event, STAMP_SCORING)
        payload = {'title': 'File:IMG 2026.jpg',
                   'description': '<p>Contractor stamp &quot;J. Smith <b>1923</b>&quot; on 21st St</p>'}
        self.assertEqual(extract_values(quest, {'diff_payload': payload}), [1923.0])

    def test_year_kind_rejects_out_of_range_values(self):
        quest = make_quest(self.event, STAMP_SCORING)
        self.assertEqual(extract_values(quest, {'description': 'stamp 1234'}), [])
        self.assertEqual(extract_values(quest, {'description': 'stamp 2099'}), [])
        # The first valid match wins, so an out-of-range year earlier in the text is skipped.
        self.assertEqual(extract_values(quest, {'description': 'lot 2099, stamped 1931'}), [1931.0])

    def test_pattern_whose_group_is_not_the_whole_value_falls_back_to_the_match(self):
        scoring = {'value': {'source': 'description', 'pattern': r'\b(18|19|20)\d{2}\b', 'kind': 'year'}}
        quest = make_quest(self.event, scoring)
        self.assertEqual(extract_values(quest, {'description': 'stamped 1947'}), [1947.0])

    def test_tag_source_reads_every_element_and_keeps_the_min_as_representative(self):
        scoring = {'value': {'source': 'tag:start_date', 'kind': 'year'},
                   'extreme_bonus': {'direction': 'min', 'points': 25}}
        quest = make_quest(self.event, scoring, criteria_type='ohm_feature')
        sub = Submission(event=self.event, quest=quest, platform='ohm', external_id='1/q1',
                         author_username='u', external_url='https://www.openhistoricalmap.org/changeset/1',
                         diff_payload={'changeset': {'id': 1, 'created_at': '2026-11-03T10:00:00Z',
                                                     'comment': '#FOSS4GNA2026'},
                                       'elements': [
                                           {'type': 'way', 'id': 1, 'tags': {'start_date': '1958'}},
                                           {'type': 'way', 'id': 2, 'tags': {'start_date': '1911-05-01'}},
                                           {'type': 'way', 'id': 3, 'tags': {'start_date': 'unknown'}},
                                           {'type': 'way', 'id': 4, 'tags': {}},
                                       ]})
        self.assertTrue(apply_extraction(quest, sub))
        self.assertEqual(sub.diff_payload['extracted_values'], [1958.0, 1911.0])
        self.assertEqual(sub.extracted_value, 1911.0)
        # Nothing new to read: a second pass changes nothing.
        self.assertFalse(apply_extraction(quest, sub))

    def test_no_scoring_value_is_a_no_op(self):
        quest = make_quest(self.event, None)
        sub = Submission(diff_payload={'description': 'stamped 1923'})
        self.assertFalse(apply_extraction(quest, sub))
        self.assertIsNone(sub.extracted_value)
        self.assertNotIn('extracted_values', sub.diff_payload)

    def test_quest_api_rejects_a_malformed_scoring_block(self):
        response = APIClient().post(reverse('quests:quest-list'), {
            'event': self.event.id, 'title': 'Bad', 'description': 'd', 'criteria_type': 'wikimedia_commons',
            'validation_rules': {'scoring': {'value': {'source': 'caption', 'pattern': '('},
                                             'per_bucket': {'size': 0, 'points': 5}}},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(response.json()['validation_rules']), 3)


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


COMMONS_SEARCH = {'query': {'search': [
    {'ns': 6, 'pageid': 501, 'title': 'File:Sidewalk stamp 21st St.jpg', 'snippet': '#FOSS4GNA2026'},
]}}
COMMONS_INFO = {'query': {'pages': {
    '501': {'pageid': 501, 'ns': 6, 'title': 'File:Sidewalk stamp 21st St.jpg',
            'imageinfo': [{'timestamp': '2026-11-03T19:30:00Z', 'user': 'Photo Alice',
                           'url': 'https://upload.wikimedia.org/s.jpg',
                           'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Sidewalk_stamp_21st_St.jpg',
                           'extmetadata': {
                               'ImageDescription': {'value': '<div class="description en">Contractor stamp '
                                                             '&quot;W. M. Kelly 1914&quot; #FOSS4GNA2026</div>',
                                                    'source': 'commons-desc-page'},
                               'ObjectName': {'value': 'Sidewalk stamp 21st St', 'source': 'original'},
                           }}],
            'categories': [{'ns': 14, 'title': 'Category:Sidewalk contractor stamps in Sacramento, California'}]},
}}}


def commons_router(url, params=None, **kwargs):
    assert url == COMMONS_API
    if params.get('list') == 'search':
        return ok(COMMONS_SEARCH)
    assert 'extmetadata' in params['iiprop']
    assert params['iiextmetadatafilter'] == 'ImageDescription|ObjectName'
    return ok(COMMONS_INFO)


@override_settings(WIKIMEDIA_COMMONS_API=COMMONS_API)
class CommonsDescriptionHarvestTests(TestCase):

    def test_harvested_description_fills_the_value(self):
        event = make_event()
        team = Team.objects.create(event=event, name='Stampers')
        TeamMembership.objects.create(team=team, user_identifier='a', wikimedia_username='Photo Alice')
        quest = make_quest(event, dict(STAMP_SCORING, value=dict(STAMP_SCORING['value'])))
        quest.validation_rules['category'] = 'Sidewalk contractor stamps in Sacramento, California'
        quest.save()

        with patch('requests.get', side_effect=commons_router):
            harvest_event_submissions(event.id)

        sub = Submission.objects.get(quest=quest)
        self.assertEqual(sub.diff_payload['description'], 'Contractor stamp "W. M. Kelly 1914" #FOSS4GNA2026')
        self.assertEqual(sub.diff_payload['object_name'], 'Sidewalk stamp 21st St')
        self.assertEqual(sub.extracted_value, 1914.0)


class ValueScoringTests(TestCase):

    def setUp(self):
        self.event = make_event()
        self.quest = make_quest(self.event, STAMP_SCORING)
        self.a = Team.objects.create(event=self.event, name='A')
        self.b = Team.objects.create(event=self.event, name='B')
        self._n = 0

    def stamp(self, team, year, verify=True):
        self._n += 1
        sub = Submission.objects.create(
            event=self.event, quest=self.quest, team=team, platform='commons',
            external_id=f'{self._n}/q{self.quest.id}', author_username='u',
            external_url='https://commons.wikimedia.org/wiki/File:x.jpg', extracted_value=year,
        )
        if verify:
            set_submission_verification(sub, True, 'Host')
        return sub

    def score(self, team):
        team.refresh_from_db()
        return team.score

    def progress(self, team):
        return QuestProgress.objects.get(team=team, quest=self.quest)

    def test_points_per_distinct_bucket(self):
        self.quest.validation_rules = {'target_count': 1, 'scoring': {'per_bucket': {'size': 10, 'points': 5}}}
        self.quest.save()
        self.stamp(self.a, 1923)
        self.stamp(self.a, 1925)
        self.stamp(self.a, 1958)
        self.stamp(self.a, 1931, verify=False)  # pending: does not count
        progress = self.progress(self.a)
        self.assertEqual(progress.buckets, [1920, 1950])
        self.assertEqual(progress.best_value, 1923.0)
        # 10 completion points + 5 for each of the 2 decades.
        self.assertEqual(progress.awarded_points, 20)
        self.assertTrue(progress.points_awarded)
        self.assertEqual(self.score(self.a), 20)

    def test_every_element_value_counts_toward_buckets(self):
        sub = self.stamp(self.a, None, verify=False)
        sub.diff_payload = {'extracted_values': [1958.0, 1911.0, 1915.0]}
        sub.extracted_value = 1911.0
        sub.save()
        set_submission_verification(sub, True)
        progress = self.progress(self.a)
        self.assertEqual(progress.buckets, [1910, 1950])
        self.assertEqual(progress.awarded_points, 10 + 10 + 25)

    def test_oldest_bonus_moves_between_teams(self):
        self.stamp(self.a, 1923)
        self.stamp(self.a, 1958)
        self.assertEqual(self.score(self.a), 10 + 10 + 25)

        self.stamp(self.b, 1911)
        self.assertEqual(self.score(self.a), 10 + 10)
        self.assertEqual(self.score(self.b), 10 + 5 + 25)
        self.assertEqual(self.progress(self.a).awarded_points, 20)
        self.assertEqual(self.progress(self.b).best_value, 1911.0)

    def test_ties_share_the_bonus(self):
        self.stamp(self.a, 1923)
        self.stamp(self.b, 1923)
        self.assertEqual(self.score(self.a), 40)
        self.assertEqual(self.score(self.b), 40)

    def test_unverifying_the_oldest_returns_the_bonus(self):
        self.stamp(self.a, 1923)
        oldest = self.stamp(self.b, 1911)
        self.assertEqual(self.score(self.a), 15)

        set_submission_verification(oldest, False)
        self.assertEqual(self.score(self.a), 40)
        self.assertEqual(self.score(self.b), 0)
        self.assertEqual(self.progress(self.b).awarded_points, 0)
        self.assertEqual(self.progress(self.b).buckets, [])

    def test_max_direction(self):
        self.quest.validation_rules = {'scoring': {'extreme_bonus': {'direction': 'max', 'points': 7}}}
        self.quest.save()
        self.stamp(self.a, 1923)
        self.stamp(self.b, 1958)
        self.assertEqual(self.score(self.a), 10)
        self.assertEqual(self.score(self.b), 17)

    def test_recompute_is_idempotent(self):
        self.stamp(self.a, 1923)
        recompute_quest_progress(self.a, self.quest)
        recompute_quest_progress(self.a, self.quest)
        self.assertEqual(self.score(self.a), 40)

    def test_host_override_through_verify(self):
        sub = self.stamp(self.a, 1923, verify=False)
        self.stamp(self.b, 1915)
        url = reverse('submissions:submission-verify', kwargs={'pk': sub.id})
        response = APIClient().post(url, {'is_verified': True, 'verified_by_username': 'host',
                                          'extracted_value': 1903}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['extracted_value'], 1903.0)
        sub.refresh_from_db()
        self.assertEqual(sub.diff_payload['extracted_values'], [1903.0])
        self.assertEqual(sub.diff_payload['value_overridden_by'], 'host')
        self.assertEqual(self.progress(self.a).buckets, [1900])
        self.assertEqual(self.score(self.a), 40)
        self.assertEqual(self.score(self.b), 15)

        # A later harvest does not overwrite the host's value.
        sub.diff_payload['description'] = 'stamped 1899'
        self.assertFalse(apply_extraction(self.quest, sub))

    def test_quest_delete_revokes_awarded_points(self):
        other = make_quest(self.event, None, points_reward=3, title='Other')
        Submission.objects.create(event=self.event, quest=other, team=self.a, platform='osm', external_id='o',
                                  author_username='u', external_url='https://example.org/1', is_verified=True)
        recompute_quest_progress(self.a, other)
        self.stamp(self.a, 1923)
        self.stamp(self.a, 1958)
        self.assertEqual(self.score(self.a), 3 + 45)

        response = APIClient().delete(reverse('quests:quest-detail', kwargs={'pk': self.quest.pk}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.score(self.a), 3)

    def test_editing_the_scoring_rule_settles_points(self):
        self.stamp(self.a, 1923)
        self.stamp(self.b, 1958)
        self.assertEqual(self.score(self.a), 40)
        rules = {'target_count': 1, 'scoring': dict(STAMP_SCORING, extreme_bonus={'direction': 'max', 'points': 25})}
        response = APIClient().patch(reverse('quests:quest-detail', kwargs={'pk': self.quest.pk}),
                                     {'validation_rules': rules}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.score(self.a), 15)
        self.assertEqual(self.score(self.b), 40)

    def test_harvested_update_recomputes_the_bonus(self):
        """upsert_submission reads the value and settles a verified submission's quest."""
        self.quest.validation_rules = {'scoring': dict(STAMP_SCORING, value={'source': 'tag:start_date', 'kind': 'year'})}
        self.quest.criteria_type = 'ohm_feature'
        self.quest.save()
        self.stamp(self.b, 1923)
        TeamMembership.objects.create(team=self.a, user_identifier='m', osm_username='mapper')
        ctx = HarvestContext(event=self.event)
        payload = {'elements': [{'type': 'way', 'id': 1, 'tags': {'start_date': '1950'}}]}
        upsert_submission(ctx, platform='ohm', quest=self.quest, external_id='77/q', external_url='https://x.org/1',
                          author_username='mapper', contributed_at=None, element_count=1, diff_payload=payload)
        sub = Submission.objects.get(external_id='77/q')
        self.assertEqual(sub.extracted_value, 1950.0)
        set_submission_verification(sub, True)
        self.assertEqual(self.score(self.a), 15)

        payload = {'elements': payload['elements'] + [{'type': 'way', 'id': 2, 'tags': {'start_date': '1890'}}]}
        self.assertEqual(upsert_submission(ctx, platform='ohm', quest=self.quest, external_id='77/q',
                                           external_url='https://x.org/1', author_username='mapper',
                                           contributed_at=None, element_count=2, diff_payload=payload), 'updated')
        sub.refresh_from_db()
        self.assertEqual(sub.extracted_value, 1890.0)
        self.assertEqual(self.score(self.a), 10 + 10 + 25)
        self.assertEqual(self.score(self.b), 15)

    def test_standings_endpoint(self):
        self.stamp(self.a, 1923)
        self.stamp(self.a, 1958)
        self.stamp(self.b, 1911)
        self.stamp(self.b, 1990, verify=False)
        response = APIClient().get(reverse('quests:quest-standings', kwargs={'pk': self.quest.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['extreme_value'], 1911.0)
        self.assertEqual(data['extreme_holder_team_ids'], [self.b.id])
        self.assertEqual(data['standings'], [
            {'team': self.b.id, 'team_name': 'B', 'awarded_points': 40, 'buckets': [1910],
             'best_value': 1911.0, 'verified_count': 1},
            {'team': self.a.id, 'team_name': 'A', 'awarded_points': 20, 'buckets': [1920, 1950],
             'best_value': 1923.0, 'verified_count': 2},
        ])

        progress = APIClient().get(reverse('teams:team-progress', kwargs={'pk': self.a.pk})).json()
        row = next(r for r in progress if r['quest'] == self.quest.id)
        self.assertEqual((row['awarded_points'], row['buckets'], row['best_value']), (20, [1920, 1950], 1923.0))
