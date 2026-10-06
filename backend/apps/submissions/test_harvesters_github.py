"""
Tests for the GitHub harvester (oss_contribution quests). No network.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests
from django.contrib.gis.geos import Polygon
from django.test import TestCase, override_settings

from apps.events.models import Event
from apps.quests.models import Quest
from apps.submissions.models import Submission
from apps.submissions.services import github_harvester
from apps.submissions.services.harvest_worker import harvest_event_submissions
from apps.teams.models import Team, TeamMembership


def ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def forbidden():
    resp = MagicMock()
    resp.status_code = 403
    err = requests.HTTPError('403 Client Error: rate limit exceeded for url: https://api.github.com/search/issues?q=x')
    err.response = resp
    resp.raise_for_status.side_effect = err
    return resp


def item(item_id, kind, owner_repo, login, created_at, title, body=''):
    data = {
        'id': item_id, 'number': item_id % 1000,
        'html_url': f'https://github.com/{owner_repo}/{"pull" if kind == "pr" else "issues"}/{item_id % 1000}',
        'repository_url': f'https://api.github.com/repos/{owner_repo}',
        'user': {'login': login}, 'title': title, 'body': body, 'state': 'open',
        'created_at': created_at,
    }
    if kind == 'pr':
        data['pull_request'] = {'url': 'https://api.github.com/x'}
    return data


PRS = {'total_count': 3, 'incomplete_results': False, 'items': [
    item(7001, 'pr', 'OSGeo/gdal', 'gh-alice', '2026-11-04T17:00:00Z', 'Fix typo', 'Found at #FOSS4GNA2026'),
    item(7002, 'pr', 'someone/random', 'gh-alice', '2026-11-04T17:10:00Z', 'Docs #FOSS4GNA2026'),
    item(7003, 'pr', 'OSGeo/grass', 'gh-bob', '2026-10-01T10:00:00Z', 'Old #FOSS4GNA2026'),
]}
ISSUES = {'total_count': 1, 'incomplete_results': False, 'items': [
    item(8001, 'issue', 'osgeo/PROJ', 'gh-alice', '2026-11-04T18:00:00Z', 'Bug', 'Repro #foss4gna2026'),
]}


class GithubHarvesterTests(TestCase):

    def setUp(self):
        github_harvester._warned_no_token = False
        self.event = Event.objects.create(
            title='Hunt', hashtag='FOSS4GNA2026',
            bounding_polygon=Polygon.from_bbox((-121.509, 38.572, -121.481, 38.590)),
            start_time=datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        self.team = Team.objects.create(event=self.event, name='Coders')
        TeamMembership.objects.create(team=self.team, user_identifier='d1', github_username='GH-Alice')
        self.calls = []

    def router(self, url, params=None, headers=None, **kwargs):
        self.calls.append({'url': url, 'params': params, 'headers': headers})
        return ok(PRS if 'is:pr' in params['q'] else ISSUES)

    @override_settings(GITHUB_TOKEN='test-token')
    def test_prs_and_issues_with_owner_filter(self):
        quest = Quest.objects.create(event=self.event, title='Ship a patch', description='x',
                                     criteria_type='oss_contribution',
                                     validation_rules={'allowed_owners': ['osgeo']})
        with patch('requests.get', side_effect=self.router):
            stats = harvest_event_submissions(self.event.id)

        self.assertEqual(stats['github']['created'], 2)
        pr = Submission.objects.get(external_id=f'7001/q{quest.id}')
        self.assertEqual(pr.platform, 'github')
        self.assertEqual(pr.author_username, 'gh-alice')
        self.assertEqual(pr.team, self.team)
        self.assertEqual(pr.external_url, 'https://github.com/OSGeo/gdal/pull/1')
        self.assertEqual(pr.diff_payload, {'kind': 'pr', 'repo': 'OSGeo/gdal', 'number': 1,
                                           'title': 'Fix typo', 'state': 'open'})
        self.assertTrue(Submission.objects.filter(external_id=f'8001/q{quest.id}').exists())

        queries = sorted(c['params']['q'] for c in self.calls)
        self.assertEqual(queries, [
            '"#FOSS4GNA2026" in:body,title is:issue created:>=2026-11-02',
            '"#FOSS4GNA2026" in:body,title is:pr created:>=2026-11-02',
        ])
        headers = self.calls[0]['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-token')
        self.assertEqual(headers['Accept'], 'application/vnd.github+json')
        self.assertIn('User-Agent', headers)

    @override_settings(GITHUB_TOKEN='')
    def test_kinds_and_no_token_warning(self):
        Quest.objects.create(event=self.event, title='PRs only', description='x',
                             criteria_type='oss_contribution', validation_rules={'kinds': ['pr']})
        with patch('requests.get', side_effect=self.router), \
                self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = harvest_event_submissions(self.event.id)
            harvest_event_submissions(self.event.id)
        self.assertEqual(len([c for c in self.calls if 'is:issue' in c['params']['q']]), 0)
        self.assertNotIn('Authorization', self.calls[0]['headers'])
        self.assertEqual(sum('GITHUB_TOKEN is not set' in m for m in logs.output), 1)
        # No owner filter: both in-window PRs count.
        self.assertEqual(stats['github']['created'], 2)

    @override_settings(GITHUB_TOKEN='')
    def test_rate_limit_403_is_counted_not_raised(self):
        Quest.objects.create(event=self.event, title='Ship', description='x',
                             criteria_type='oss_contribution', validation_rules={})
        with patch('requests.get', return_value=forbidden()), \
                self.assertLogs('apps.submissions.harvest', level='WARNING') as logs:
            stats = harvest_event_submissions(self.event.id)
        self.assertEqual(stats['github']['errors'], 2)
        self.assertEqual(stats['github']['created'], 0)
        self.assertNotIn('api.github.com', '\n'.join(logs.output))
