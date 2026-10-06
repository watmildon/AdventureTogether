#!/usr/bin/env python
"""
End-to-end smoke test for AdventureTogether against a running local backend.

Exercises the participant and host flows the FOSS4G NA 2026 event depends on:
seeding the event, forming a team with contributor usernames, a GPS check-in
that auto-verifies and scores, counted quests advancing through host
verification, the leaderboard, and (when OVERPASS_URL is set) a dry-run harvest
against the real external APIs.

Usage (backend running on 127.0.0.1:8000, env sourced as in documentation/local_setup.md):

    cd backend && .venv/bin/python ../scripts/e2e_smoke.py [--base http://127.0.0.1:8000] [--keep]

Exit code 0 means every assertion passed. The script creates a throwaway team and
cleans it up unless --keep is given. It never prints OVERPASS_URL.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent / 'backend'
FIXTURE = BACKEND_DIR / 'fixtures' / 'foss4gna_2026.json'
SCHEDULE = BACKEND_DIR / 'fixtures' / 'foss4gna_2026_schedule.json'
EVENT_SLUG = 'foss4gna-2026'
USER_ID = 'e2e-smoke-user'

PASSED = 0


def check(condition, message):
    """Records one assertion; prints PASS/FAIL and aborts on failure."""
    global PASSED
    if condition:
        PASSED += 1
        print(f'  PASS  {message}')
    else:
        print(f'  FAIL  {message}')
        sys.exit(1)


def manage(*args):
    """Runs a manage.py command with the backend venv and returns stdout."""
    python = BACKEND_DIR / '.venv' / 'bin' / 'python'
    result = subprocess.run(
        [str(python), 'manage.py', *args],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Never echo stderr wholesale: requests exceptions can embed endpoint URLs.
        print(f'  manage.py {" ".join(args)} failed with exit {result.returncode}')
        sys.exit(1)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--keep', action='store_true', help='leave the throwaway team in place')
    args = parser.parse_args()
    api = args.base.rstrip('/') + '/api'

    print('1. Backend health')
    health = requests.get(f'{api}/health/', timeout=10).json()
    check(health.get('status') == 'healthy', f'backend healthy on {health.get("database_engine")}')

    print('2. Seed the FOSS4G NA 2026 event (idempotent)')
    out = manage('seed_event', str(FIXTURE), '--schedule-json', str(SCHEDULE))
    check('Quests:' in out, 'seed_event ran')
    events = requests.get(f'{api}/events/', timeout=10).json()['results']
    event = next((e for e in events if e['slug'] == EVENT_SLUG), None)
    check(event is not None, f'event "{EVENT_SLUG}" exists')
    event_id = event['id']
    quests = requests.get(f'{api}/quests/', params={'event': event_id}, timeout=10).json()
    quests = quests.get('results', quests)
    by_title = {q['title']: q for q in quests}
    check(len(quests) >= 20, f'{len(quests)} quests seeded')
    ohm = by_title.get('Alkali Flat, then and now')
    check(ohm and ohm['inspired_by'].get('title', '').startswith('OpenHistoricalMap'),
          'inspired_by expanded from the pretalx export')

    print('3. Team formation with contributor usernames')
    team = requests.post(f'{api}/teams/', json={'event': event_id, 'name': 'E2E Smoke Team'}, timeout=10)
    if team.status_code == 400:  # left over from an earlier --keep run
        teams = requests.get(f'{api}/teams/', params={'event': event_id}, timeout=10).json()
        teams = teams.get('results', teams)
        team_obj = next(t for t in teams if t['name'] == 'E2E Smoke Team')
    else:
        check(team.status_code == 201, 'team created')
        team_obj = team.json()
    team_id = team_obj['id']
    joined = requests.post(f'{api}/teams/join/', json={
        'join_code': team_obj['join_code'], 'user_identifier': USER_ID, 'display_name': 'E2E Smoke',
        'osm_username': 'e2e_osm', 'wikimedia_username': 'E2E Wiki', 'github_username': 'e2e-gh',
    }, timeout=10)
    check(joined.status_code in (200, 201), 'joined team with join code')
    membership = joined.json()['membership']
    check(membership.get('osm_username') == 'e2e_osm', 'osm_username stored on membership')

    print('4. GPS check-in auto-verifies and scores')
    capitol = by_title['Capitol check-in']
    lon, lat = capitol['target_geometry']['coordinates']
    ping = requests.post(f'{api}/locations/ping/', json={
        'event': event_id, 'user_identifier': USER_ID, 'display_name': 'E2E Smoke',
        'longitude': lon + 0.0001, 'latitude': lat, 'visibility': 'team', 'is_foreground': True,
    }, timeout=10)
    check(ping.status_code == 200, 'ping accepted')
    checkins = ping.json().get('checkins', [])
    hit = next((c for c in checkins if c['quest'] == capitol['id']), None)
    check(hit is not None and hit['status'] == 'verified', f'ping response reports Capitol check-in verified ({hit})')
    listed = requests.get(f'{api}/locations/checkins/', params={'event': event_id, 'user_identifier': USER_ID}, timeout=10).json()
    check(any(c['quest'] == capitol['id'] and c['status'] == 'verified' for c in listed), 'checkins endpoint lists it')
    progress = requests.get(f'{api}/teams/{team_id}/progress/', timeout=10).json()
    row = next(p for p in progress if p['quest'] == capitol['id'])
    check(row['completed_at'] is not None and row['points_awarded'], 'team progress shows the check-in complete')
    board = requests.get(f'{api}/events/{event_id}/leaderboard/', timeout=10).json()
    mine = next(t for t in board if t['id'] == team_id)
    check(mine['score'] == capitol['points_reward'], f'leaderboard score is {mine["score"]}')
    far = requests.post(f'{api}/locations/ping/', json={
        'event': event_id, 'user_identifier': USER_ID, 'display_name': 'E2E Smoke',
        'longitude': lon + 0.02, 'latitude': lat, 'visibility': 'team', 'is_foreground': True,
    }, timeout=10).json()
    check(not any(c['quest'] == capitol['id'] for c in far.get('checkins', [])), 'a far-away ping is not in range')

    print('5. Counted quest advances through host verification')
    racks = by_title['Lock it up']
    target = racks['target_count']
    first = requests.post(f'{api}/submissions/', json={
        'event': event_id, 'quest': racks['id'], 'team': team_id, 'platform': 'osm',
        'external_id': f'e2e-{int(time.time())}-a/q{racks["id"]}', 'author_username': 'e2e_osm',
        'external_url': 'https://www.openstreetmap.org/changeset/1', 'element_count': target - 1,
        'diff_payload': {'note': 'e2e'},
    }, timeout=10)
    check(first.status_code == 201, 'first submission created')
    v1 = requests.post(f'{api}/submissions/{first.json()["id"]}/verify/', json={'is_verified': True, 'verified_by_username': 'e2e-host'}, timeout=10)
    check(v1.status_code == 200, 'first submission verified')
    row = next(p for p in requests.get(f'{api}/teams/{team_id}/progress/', timeout=10).json() if p['quest'] == racks['id'])
    check(row['count'] == target - 1 and row['completed_at'] is None, f'progress {row["count"]}/{target}, not complete yet')
    second = requests.post(f'{api}/submissions/', json={
        'event': event_id, 'quest': racks['id'], 'team': team_id, 'platform': 'osm',
        'external_id': f'e2e-{int(time.time())}-b/q{racks["id"]}', 'author_username': 'e2e_osm',
        'external_url': 'https://www.openstreetmap.org/changeset/2', 'element_count': 1,
        'diff_payload': {'note': 'e2e'},
    }, timeout=10)
    requests.post(f'{api}/submissions/{second.json()["id"]}/verify/', json={'is_verified': True}, timeout=10)
    row = next(p for p in requests.get(f'{api}/teams/{team_id}/progress/', timeout=10).json() if p['quest'] == racks['id'])
    check(row['completed_at'] is not None, f'progress {row["count"]}/{target} complete')
    mine = next(t for t in requests.get(f'{api}/events/{event_id}/leaderboard/', timeout=10).json() if t['id'] == team_id)
    check(mine['score'] == capitol['points_reward'] + racks['points_reward'], f'score now {mine["score"]}')
    requests.post(f'{api}/submissions/{second.json()["id"]}/verify/', json={'is_verified': False}, timeout=10)
    mine = next(t for t in requests.get(f'{api}/events/{event_id}/leaderboard/', timeout=10).json() if t['id'] == team_id)
    check(mine['score'] == capitol['points_reward'], 'revoking a submission takes the quest points back')

    print('6. Harvest dry-run against real external APIs')
    if os.environ.get('OVERPASS_URL'):
        out = manage('harvest_event', str(event_id), '--dry-run')
        try:
            stats = json.loads(out[out.index('{'):])
        except ValueError:
            stats = None
        check(stats is not None, 'harvest_event --dry-run returned JSON stats')
        print('        ' + json.dumps({k: v for k, v in stats.items() if k != 'would_create'})[:400])
    else:
        print('  SKIP  OVERPASS_URL not set; run with OVERPASS_URL="$(cat ~/.overpassurl)" to include harvesting')

    if not args.keep:
        print('7. Cleanup')
        deleted = requests.delete(f'{api}/teams/{team_id}/', timeout=10)
        check(deleted.status_code == 204, 'throwaway team deleted')

    print(f'\nAll {PASSED} checks passed.')


if __name__ == '__main__':
    main()
