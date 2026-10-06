"""
Tests for the Wikimedia Commons and Wikidata harvesters. No network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Polygon
from django.test import TestCase, override_settings

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.submissions.services.wikidata_harvester import properties_mentioned
from apps.teams.models import Team, TeamMembership

COMMONS_API = 'https://commons.invalid/w/api.php'
WIKIDATA_API = 'https://wikidata.invalid/w/api.php'


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def make_event():
    return Event.objects.create(
        title='Hunt', hashtag='FOSS4GNA2026',
        bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
        start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
    )


COMMONS_SEARCH = {'query': {'search': [
    {'ns': 6, 'pageid': 111, 'title': 'File:Public Market facade.jpg', 'snippet': 'J St #FOSS4GNA2026'},
    {'ns': 6, 'pageid': 222, 'title': 'File:Old upload.jpg', 'snippet': '#FOSS4GNA2026'},
]}}
COMMONS_INFO_1 = {
    'continue': {'clcontinue': '111|Sacramento', 'continue': '||imageinfo'},
    'query': {'pages': {
        '111': {'pageid': 111, 'ns': 6, 'title': 'File:Public Market facade.jpg',
                'imageinfo': [{'timestamp': '2026-11-02T19:30:00Z', 'user': 'Photo Alice',
                               'url': 'https://upload.wikimedia.org/a.jpg',
                               'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Public_Market_facade.jpg'}],
                'categories': [{'ns': 14, 'title': 'Category:Julia Morgan buildings'}]},
        '222': {'pageid': 222, 'ns': 6, 'title': 'File:Old upload.jpg',
                'imageinfo': [{'timestamp': '2025-05-01T10:00:00Z', 'user': 'Photo Alice',
                               'url': 'https://upload.wikimedia.org/b.jpg',
                               'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Old_upload.jpg'}]},
    }},
}
COMMONS_INFO_2 = {'query': {'pages': {
    '111': {'pageid': 111, 'ns': 6, 'title': 'File:Public Market facade.jpg',
            'categories': [{'ns': 14, 'title': 'Category:Sacramento,_California'}]},
    '222': {'pageid': 222, 'ns': 6, 'title': 'File:Old upload.jpg'},
}}}


def commons_router(url, params=None, **kwargs):
    assert url == COMMONS_API
    if params.get('list') == 'search':
        assert params['srnamespace'] == '6'
        return ok(COMMONS_SEARCH)
    assert params['prop'] == 'imageinfo|categories'
    assert params['iiprop'] == 'user|timestamp|url'
    return ok(COMMONS_INFO_2 if 'clcontinue' in params else COMMONS_INFO_1)


@override_settings(WIKIMEDIA_COMMONS_API=COMMONS_API)
class CommonsHarvesterTests(TestCase):

    def setUp(self):
        self.event = make_event()
        self.team = Team.objects.create(event=self.event, name='Shutterbugs')
        TeamMembership.objects.create(team=self.team, user_identifier='d1', wikimedia_username='photo alice')

    def test_uploader_time_and_category_are_resolved(self):
        any_photo = Quest.objects.create(event=self.event, title='Any photo', description='x',
                                         criteria_type='wikimedia_commons', validation_rules={})
        sacramento = Quest.objects.create(event=self.event, title='Sacramento', description='x',
                                          criteria_type='wikimedia_commons',
                                          validation_rules={'category': 'Category:Sacramento, California'})
        memorials = Quest.objects.create(event=self.event, title='Memorials', description='x',
                                         criteria_type='wikimedia_commons',
                                         validation_rules={'category': 'Capitol Park memorials'})
        with patch('requests.get', side_effect=commons_router):
            stats = harvest_event_submissions(self.event.id)

        self.assertEqual(stats['commons']['created'], 2)
        sub = Submission.objects.get(external_id=f'111/q{any_photo.id}')
        self.assertEqual(sub.author_username, 'Photo Alice')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 2, 19, 30, tzinfo=timezone.utc))
        self.assertEqual(sub.external_url, 'https://commons.wikimedia.org/wiki/File:Public_Market_facade.jpg')
        self.assertIn('Category:Sacramento,_California', sub.diff_payload['categories'])
        self.assertTrue(Submission.objects.filter(external_id=f'111/q{sacramento.id}').exists())
        self.assertFalse(Submission.objects.filter(quest=memorials).exists())
        # Uploaded before the event window.
        self.assertFalse(Submission.objects.filter(external_id__startswith='222/').exists())
        self.assertFalse(Submission.objects.filter(author_username='Wikimedia Uploader').exists())


WD_SEARCH = {'query': {'search': [{'ns': 0, 'pageid': 42, 'title': 'Q42'}]}}
WD_Q42_REVS = {'query': {'pages': {'42': {'pageid': 42, 'title': 'Q42', 'revisions': [
    {'revid': 1001, 'parentid': 1000, 'user': 'WikiAlice', 'timestamp': '2026-11-03T17:00:00Z',
     'comment': '/* wbsetclaim-create:2||1 */ [[Property:P18]]: x.jpg #FOSS4GNA2026'},
    {'revid': 1000, 'parentid': 999, 'user': 'Bot', 'timestamp': '2026-11-03T16:00:00Z',
     'comment': 'bot edit'},
]}}}}
WD_CONTRIBS = {'query': {'usercontribs': [
    {'userid': 9, 'user': 'WikiAlice', 'pageid': 99, 'revid': 2002, 'title': 'Q99',
     'timestamp': '2026-11-04T09:00:00Z', 'comment': 'label fix #FOSS4GNA2026'},
    {'userid': 9, 'user': 'WikiAlice', 'pageid': 42, 'revid': 1001, 'title': 'Q42',
     'timestamp': '2026-11-03T17:00:00Z', 'comment': '/* wbsetclaim-create:2||1 */ #FOSS4GNA2026'},
    {'userid': 9, 'user': 'WikiAlice', 'pageid': 98, 'revid': 2003, 'title': 'Q98',
     'timestamp': '2026-11-04T09:30:00Z', 'comment': 'no tag'},
]}}
WD_VENUE_REVS = {'query': {'pages': {'111393295': {'title': 'Q111393295', 'revisions': [
    {'revid': 3001, 'user': 'WikiAlice', 'timestamp': '2026-11-04T18:00:00Z',
     'comment': '/* wbsetclaim-create:2||1 */ [[Property:P84]]: [[Q274663]], #FOSS4GNA2026'},
    {'revid': 3002, 'user': 'WikiAlice', 'timestamp': '2026-11-04T18:05:00Z',
     'comment': '/* wbsetclaim-create:2||1 */ [[Property:P571]]: 1923'},
    {'revid': 3003, 'user': 'WikiAlice', 'timestamp': '2026-11-04T18:10:00Z',
     'comment': '/* wbsetclaim-create:2||1 */ [[Property:P31]]: [[Q41176]] #FOSS4GNA2026'},
    {'revid': 3004, 'user': 'WikiAlice', 'timestamp': '2026-11-04T18:15:00Z',
     'comment': '/* wbsetclaim-create:2||1 */ [[Property:P8410]]: x #FOSS4GNA2026'},
]}}}}


@override_settings(WIKIDATA_API=WIKIDATA_API)
class WikidataHarvesterTests(TestCase):

    def setUp(self):
        self.event = make_event()
        self.team = Team.objects.create(event=self.event, name='Wikidatans')
        TeamMembership.objects.create(team=self.team, user_identifier='d1', wikimedia_username='WikiAlice')
        self.calls = []

    def router(self, url, params=None, **kwargs):
        assert url == WIKIDATA_API
        self.calls.append(params)
        if params.get('list') == 'search':
            return ok(WD_SEARCH)
        if params.get('list') == 'usercontribs':
            assert params['ucuser'] == 'WikiAlice'
            return ok(WD_CONTRIBS)
        assert params['rvprop'] == 'ids|user|timestamp|comment'
        if params['titles'] == 'Q42':
            assert params['rvlimit'] == '20'
            return ok(WD_Q42_REVS)
        if params['titles'] == 'Q111393295':
            assert params['rvlimit'] == '100'
            return ok(WD_VENUE_REVS)
        raise AssertionError(params)

    def test_entry_quests_get_one_submission_per_hashtag_revision(self):
        quest = Quest.objects.create(event=self.event, title='Any edit', description='x',
                                     criteria_type='wikidata_entry', validation_rules={})
        with patch('requests.get', side_effect=self.router):
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['wikidata']['created'], 2)
        sub = Submission.objects.get(platform='wikidata', external_id='1001')
        self.assertEqual(sub.author_username, 'WikiAlice')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.quest, quest)
        self.assertEqual(sub.external_url, 'https://www.wikidata.org/w/index.php?diff=1001')
        self.assertEqual(sub.diff_payload['entity_id'], 'Q42')
        self.assertTrue(Submission.objects.filter(external_id='2002').exists())
        rev_call = next(c for c in self.calls if c.get('titles') == 'Q42')
        self.assertEqual((rev_call['rvstart'], rev_call['rvend']), ('2026-11-05T02:00:00Z', '2026-11-02T16:00:00Z'))

    def test_statement_quest_requires_hashtag_and_property(self):
        quest = Quest.objects.create(event=self.event, title='Julia Morgan', description='x',
                                     criteria_type='wikidata_statement',
                                     validation_rules={'qid': 'Q111393295', 'properties': ['P84', 'P571']})
        with patch('requests.get', side_effect=self.router):
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['wikidata']['created'], 1)
        sub = Submission.objects.get(platform='wikidata')
        self.assertEqual(sub.external_id, f'3001/q{quest.id}')
        self.assertEqual(sub.diff_payload['qid'], 'Q111393295')
        self.assertEqual(sub.diff_payload['properties_touched'], ['P84'])
        self.assertEqual(sub.team, self.team)
        # Only the named item was queried; no search for statement-only events.
        self.assertEqual([c.get('titles') for c in self.calls], ['Q111393295'])

    def test_statement_quest_without_qid_is_skipped_with_warning(self):
        Quest.objects.create(event=self.event, title='New item', description='x',
                             criteria_type='wikidata_statement', validation_rules={})
        with patch('requests.get', side_effect=self.router):
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(self.calls, [])
        self.assertTrue(any('no qid' in w for w in stats['warnings']))

    def test_properties_mentioned_whole_tokens(self):
        self.assertEqual(properties_mentioned('[[Property:P84]]: x', ['P84', 'p571']), ['P84'])
        self.assertEqual(properties_mentioned('[[Property:P8410]]', ['P84']), [])
        self.assertEqual(properties_mentioned('added P571 and P84', ['P84', 'P571']), ['P84', 'P571'])
