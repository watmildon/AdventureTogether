"""
Tests for the wikidata_area harvester (statements on items located in the quest area). No network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Polygon
from django.test import TestCase, override_settings

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.submissions.services.wikidata_harvester import area_properties, is_claim_summary
from apps.teams.models import Team, TeamMembership

WIKIDATA_API = 'https://wikidata.invalid/w/api.php'

# Inside the event perimeter (-121.509..-121.481, 38.572..38.590) and outside it.
INSIDE = (38.5799, -121.4940)
OUTSIDE = (38.6500, -121.4000)


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def contrib(revid, qid, comment, timestamp='2026-11-03T17:00:00Z', user='WikiAlice'):
    return {'userid': 9, 'user': user, 'pageid': revid, 'revid': revid, 'ns': 0, 'title': qid,
            'timestamp': timestamp, 'comment': comment}


def entity(qid, coords=None, label=None):
    claims = {}
    if coords:
        claims['P625'] = [{'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {
            'type': 'globecoordinate',
            'value': {'latitude': coords[0], 'longitude': coords[1], 'globe': 'http://www.wikidata.org/entity/Q2'},
        }}}]
    data = {'id': qid, 'claims': claims}
    if label:
        data['labels'] = {'en': {'language': 'en', 'value': label}}
    return data


P18_CREATE = '/* wbcreateclaim-create:1| */ [[Property:P18]]: Tower Theatre.jpg, #wikishootme'
P18_UI = '/* wbsetclaim-create:2||1 */ [[Property:P18]]: Tower Theatre 2.jpg'
P373_CREATE = '/* wbsetclaim-create:2||1 */ [[Property:P373]]: Tower Theatre (Sacramento)'
P31_CREATE = '/* wbsetclaim-create:2||1 */ [[Property:P31]]: [[Q24354]]'
P18_REMOVE = '/* wbremoveclaims-remove:1| */ [[Property:P18]]: Tower Theatre.jpg'


@override_settings(WIKIDATA_API=WIKIDATA_API)
class WikidataAreaHarvesterTests(TestCase):

    def setUp(self):
        self.event = Event.objects.create(
            title='Hunt', hashtag='FOSS4GNA2026',
            bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
            start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        self.team = Team.objects.create(event=self.event, name='Shutterbugs')
        TeamMembership.objects.create(team=self.team, user_identifier='d1', wikimedia_username='WikiAlice')
        self.quest = Quest.objects.create(event=self.event, title='Picture this', description='x',
                                          criteria_type='wikidata_area',
                                          validation_rules={'properties': ['P18'], 'target_count': 3})
        self.contribs = []          # usercontribs pages for WikiAlice, served in order
        self.entities = {}          # qid -> entity
        self.calls = []

    def router(self, url, params=None, **kwargs):
        assert url == WIKIDATA_API
        self.calls.append(params)
        if params.get('list') == 'usercontribs':
            assert params['ucuser'] == 'WikiAlice'
            assert params['uclimit'] == '100'
            assert params['ucprop'] == 'ids|title|timestamp|comment'
            assert (params['ucstart'], params['ucend']) == ('2026-11-05T02:00:00Z', '2026-11-02T16:00:00Z')
            page = sum(1 for c in self.calls if c.get('list') == 'usercontribs') - 1
            if page > 0:
                assert params['uccontinue'] == f'cont-{page}'
            return ok(self.contribs[page])
        assert params['action'] == 'wbgetentities'
        assert 'claims' in params['props'].split('|')
        ids = params['ids'].split('|')
        assert len(ids) <= 50
        return ok({'entities': {q: self.entities.get(q, {'id': q, 'missing': ''}) for q in ids}})

    def page(self, items, cont=None):
        data = {'query': {'usercontribs': items}}
        if cont:
            data['continue'] = {'uccontinue': cont, 'continue': '-||'}
        return data

    def harvest(self):
        with patch('requests.get', side_effect=self.router):
            return harvest_event_submissions(self.event.id)

    def entity_calls(self):
        return [c for c in self.calls if c.get('action') == 'wbgetentities']

    def test_p18_creation_inside_the_area_is_credited(self):
        self.contribs = [self.page([contrib(5001, 'Q100', P18_CREATE)])]
        self.entities = {'Q100': entity('Q100', INSIDE, 'Tower Theatre')}
        stats = self.harvest()

        self.assertEqual(stats['wikidata']['created'], 1)
        self.assertEqual(stats['wikidata']['entity_lookups'], 1)
        sub = Submission.objects.get(platform='wikidata')
        self.assertEqual(sub.external_id, f'Q100/q{self.quest.id}')
        self.assertEqual(sub.external_url, 'https://www.wikidata.org/wiki/Q100')
        self.assertEqual(sub.author_username, 'WikiAlice')
        self.assertEqual(sub.team, self.team)
        self.assertEqual(sub.element_count, 1)
        self.assertEqual(sub.contributed_at, datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(sub.diff_payload, {
            'qid': 'Q100', 'label': 'Tower Theatre', 'properties_touched': ['P18'], 'revid': '5001',
            'comment': P18_CREATE, 'lat': INSIDE[0], 'lon': INSIDE[1],
        })

    def test_same_item_edited_twice_yields_one_submission(self):
        self.contribs = [self.page([
            contrib(5003, 'Q100', P18_UI, timestamp='2026-11-04T09:00:00Z'),
            contrib(5001, 'Q100', P18_CREATE, timestamp='2026-11-03T17:00:00Z'),
        ])]
        self.entities = {'Q100': entity('Q100', INSIDE)}
        stats = self.harvest()
        self.assertEqual(stats['wikidata']['created'], 1)
        sub = Submission.objects.get(platform='wikidata')
        # The earliest qualifying edit is the one credited.
        self.assertEqual(sub.diff_payload['revid'], '5001')
        self.assertNotIn('label', sub.diff_payload)
        # Only one lookup for the item even though it was edited twice.
        self.assertEqual(self.entity_calls()[0]['ids'], 'Q100')

    def test_item_outside_the_area_or_without_coordinates_is_ignored(self):
        self.contribs = [self.page([contrib(5001, 'Q100', P18_CREATE), contrib(5002, 'Q200', P18_CREATE)])]
        self.entities = {'Q100': entity('Q100', OUTSIDE), 'Q200': entity('Q200')}
        stats = self.harvest()
        self.assertEqual(stats['wikidata']['created'], 0)
        self.assertFalse(Submission.objects.exists())

    def test_comment_touching_another_property_or_removing_is_ignored(self):
        self.contribs = [self.page([
            contrib(5001, 'Q100', P31_CREATE),
            contrib(5002, 'Q100', P18_REMOVE),
            contrib(5003, 'Q100', 'Changed label [[Property:P18]]'),
        ])]
        self.entities = {'Q100': entity('Q100', INSIDE)}
        stats = self.harvest()
        self.assertEqual(stats['wikidata']['created'], 0)
        # Nothing qualified on the summary, so no entity was looked up.
        self.assertEqual(self.entity_calls(), [])

    def test_property_list_is_configurable(self):
        self.quest.validation_rules = {'properties': ['P18', 'P373'], 'target_count': 3}
        self.quest.save()
        self.contribs = [self.page([
            contrib(5001, 'Q100', P373_CREATE),
            contrib(5002, 'Q200', P18_CREATE),
            contrib(5003, 'Q300', P31_CREATE),
        ])]
        self.entities = {q: entity(q, INSIDE) for q in ('Q100', 'Q200', 'Q300')}
        self.harvest()
        self.assertEqual(set(Submission.objects.values_list('external_id', flat=True)),
                         {f'Q100/q{self.quest.id}', f'Q200/q{self.quest.id}'})
        self.assertEqual(Submission.objects.get(external_id__startswith='Q100/').diff_payload['properties_touched'],
                         ['P373'])

    def test_more_than_fifty_items_are_looked_up_in_two_batches(self):
        qids = [f'Q{1000 + i}' for i in range(60)]
        self.contribs = [self.page([contrib(6000 + i, qid, P18_CREATE) for i, qid in enumerate(qids)])]
        self.entities = {qid: entity(qid, INSIDE) for qid in qids}
        stats = self.harvest()
        calls = self.entity_calls()
        self.assertEqual([len(c['ids'].split('|')) for c in calls], [50, 10])
        self.assertEqual(stats['wikidata']['entity_lookups'], 2)
        self.assertEqual(stats['wikidata']['created'], 60)

    def test_member_without_wikimedia_username_contributes_nothing(self):
        TeamMembership.objects.update(wikimedia_username='')
        stats = self.harvest()
        self.assertEqual(self.calls, [])
        self.assertEqual(stats['wikidata']['created'], 0)
        self.assertTrue(any('Wikimedia username' in w for w in stats['warnings']))

    def test_paging_follows_uccontinue_and_stops_without_it(self):
        self.contribs = [
            self.page([contrib(5001, 'Q100', P18_CREATE)], cont='cont-1'),
            self.page([contrib(5002, 'Q200', P18_CREATE)]),
            self.page([contrib(5003, 'Q300', P18_CREATE)]),  # never requested
        ]
        self.entities = {q: entity(q, INSIDE) for q in ('Q100', 'Q200', 'Q300')}
        stats = self.harvest()
        self.assertEqual(sum(1 for c in self.calls if c.get('list') == 'usercontribs'), 2)
        self.assertEqual(stats['wikidata']['created'], 2)

    def test_paging_is_capped_at_five_pages(self):
        self.contribs = [self.page([], cont=f'cont-{i + 1}') for i in range(6)]
        stats = self.harvest()
        self.assertEqual(sum(1 for c in self.calls if c.get('list') == 'usercontribs'), 5)
        self.assertTrue(any('stopped at 5 pages' in w for w in stats['warnings']))

    def test_require_hashtag_needs_it_in_the_summary(self):
        self.quest.validation_rules = {'properties': ['P18'], 'require_hashtag': True}
        self.quest.save()
        self.contribs = [self.page([
            contrib(5001, 'Q100', P18_CREATE),
            contrib(5002, 'Q200', P18_UI + ' #FOSS4GNA2026'),
        ])]
        self.entities = {q: entity(q, INSIDE) for q in ('Q100', 'Q200')}
        self.harvest()
        self.assertEqual(list(Submission.objects.values_list('external_id', flat=True)),
                         [f'Q200/q{self.quest.id}'])

    def test_edits_outside_the_window_are_ignored(self):
        self.contribs = [self.page([contrib(5001, 'Q100', P18_CREATE, timestamp='2026-11-05T03:00:00Z')])]
        self.entities = {'Q100': entity('Q100', INSIDE)}
        stats = self.harvest()
        self.assertEqual(stats['wikidata']['created'], 0)

    def test_helpers(self):
        self.assertTrue(is_claim_summary(P18_CREATE))
        self.assertTrue(is_claim_summary(P18_UI))
        self.assertTrue(is_claim_summary('/* wbsetclaim-update:2||1 */ [[Property:P18]]: b.jpg'))
        self.assertFalse(is_claim_summary(P18_REMOVE))
        self.assertFalse(is_claim_summary('/* wbeditentity-update:0| */'))
        self.quest.validation_rules = {}
        self.assertEqual(area_properties(self.quest), ['P18'])
        self.quest.validation_rules = {'properties': ['p373', 'x"} DROP', 'P18', 'P373']}
        self.assertEqual(area_properties(self.quest), ['P373', 'P18'])
