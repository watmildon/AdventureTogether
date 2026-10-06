#!/usr/bin/env python
"""
End-to-end smoke test for AdventureTogether against a running local backend.

Exercises the participant and host flows the FOSS4G NA 2026 event depends on:
seeding the event, forming a team with contributor usernames, a GPS check-in
that auto-verifies and scores, counted quests advancing through host
verification, a value-scoring quest (per-decade points and an oldest-stamp bonus
that moves between teams), the leaderboard, and (when OVERPASS_URL is set) a
dry-run harvest against the real external APIs.

Usage (backend running on 127.0.0.1:8000, env sourced as in documentation/local_setup.md):

    cd backend && .venv/bin/python ../scripts/e2e_smoke.py [--base http://127.0.0.1:8000] [--keep]

Exit code 0 means every assertion passed. The script creates a throwaway team and
cleans it up unless --keep is given (the temporary value-scoring quest and its
second team are always removed). It never prints OVERPASS_URL.
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


def progress_row(api, team_id, quest_id):
    rows = requests.get(f'{api}/teams/{team_id}/progress/', timeout=10).json()
    return next(p for p in rows if p['quest'] == quest_id)


def leaderboard_score(api, event_id, team_id):
    board = requests.get(f'{api}/events/{event_id}/leaderboard/', timeout=10).json()
    return next(t for t in board if t['id'] == team_id)['score']


def harvest_dry_run(event_id):
    """Runs manage.py harvest_event --dry-run and returns the parsed stats, or None."""
    out = manage('harvest_event', str(event_id), '--dry-run')
    try:
        return json.loads(out[out.index('{'):])
    except ValueError:
        return None


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

    print('5b. Value-scoring quest: points per decade and the oldest-stamp bonus')
    run = int(time.time())
    stamps = requests.post(f'{api}/quests/', json={
        'event': event_id, 'title': f'E2E stamps {run} (temporary)', 'description': 'temporary',
        'criteria_type': 'wikimedia_commons', 'target_geometry': None, 'points_reward': 10,
        'validation_rules': {'target_count': 1, 'scoring': {
            'value': {'source': 'description', 'pattern': r'\b((?:18|19|20)\d{2})\b', 'kind': 'year'},
            'per_bucket': {'size': 10, 'points': 5},
            'extreme_bonus': {'direction': 'min', 'points': 25},
        }},
    }, timeout=10)
    check(stamps.status_code == 201, 'temporary value-scoring quest created')
    stamps_id = stamps.json()['id']

    def stamp(on_team, year, tag):
        sub = requests.post(f'{api}/submissions/', json={
            'event': event_id, 'quest': stamps_id, 'team': on_team, 'platform': 'commons',
            'external_id': f'e2e-{run}-stamp-{tag}/q{stamps_id}', 'author_username': 'E2E Wiki',
            'external_url': 'https://commons.wikimedia.org/wiki/File:E2E_stamp.jpg',
            'diff_payload': {'description': f'e2e stamp {year}'}, 'extracted_value': year,
        }, timeout=10)
        check(sub.status_code == 201 and sub.json()['extracted_value'] == year, f'stamp {year} submitted')
        verified = requests.post(f'{api}/submissions/{sub.json()["id"]}/verify/', json={'is_verified': True}, timeout=10)
        check(verified.status_code == 200, f'stamp {year} verified')

    before = leaderboard_score(api, event_id, team_id)
    stamp(team_id, 1923, 'a')
    stamp(team_id, 1958, 'b')
    row = progress_row(api, team_id, stamps_id)
    check(row['awarded_points'] == 10 + 5 * 2 + 25 and row['buckets'] == [1920, 1950] and row['best_value'] == 1923,
          f'first team holds 45 from the quest ({row["awarded_points"]}, buckets {row["buckets"]}, best {row["best_value"]})')
    check(leaderboard_score(api, event_id, team_id) == before + 45, 'leaderboard includes the 45')

    rivals = requests.post(f'{api}/teams/', json={'event': event_id, 'name': 'E2E Smoke Rivals'}, timeout=10)
    if rivals.status_code == 400:  # left over from an aborted run
        teams = requests.get(f'{api}/teams/', params={'event': event_id}, timeout=10).json()
        rivals_id = next(t for t in teams.get('results', teams) if t['name'] == 'E2E Smoke Rivals')['id']
    else:
        check(rivals.status_code == 201, 'second team created')
        rivals_id = rivals.json()['id']
    rivals_before = leaderboard_score(api, event_id, rivals_id)
    stamp(rivals_id, 1911, 'c')
    first_row = progress_row(api, team_id, stamps_id)
    rival_row = progress_row(api, rivals_id, stamps_id)
    check(first_row['awarded_points'] == 20, f'bonus left the first team ({first_row["awarded_points"]})')
    check(rival_row['awarded_points'] == 10 + 5 + 25, f'bonus moved to the second team ({rival_row["awarded_points"]})')
    check(leaderboard_score(api, event_id, team_id) == before + 20, 'first team score dropped by the bonus')
    standings = requests.get(f'{api}/quests/{stamps_id}/standings/', timeout=10).json()
    check(standings['extreme_holder_team_ids'] == [rivals_id] and standings['extreme_value'] == 1911
          and standings['standings'][0]['team'] == rivals_id, 'standings show the second team holding the oldest stamp')

    deleted = requests.delete(f'{api}/quests/{stamps_id}/', timeout=10)
    check(deleted.status_code == 204, 'temporary quest deleted')
    check(leaderboard_score(api, event_id, team_id) == before, 'deleting the quest revoked the first team\'s points')
    check(leaderboard_score(api, event_id, rivals_id) == rivals_before, 'deleting the quest revoked the second team\'s points')
    deleted = requests.delete(f'{api}/teams/{rivals_id}/', timeout=10)
    check(deleted.status_code == 204, 'second team deleted')

    print('6. Harvest dry-run against real external APIs')
    if os.environ.get('OVERPASS_URL'):
        # 6a. The real event: its window is in the future until the conference, so
        # nothing should match, but every platform must run without errors.
        stats = harvest_dry_run(event_id)
        check(stats is not None and stats.get('found'), 'harvest_event --dry-run returned stats for the seeded event')
        check(stats['summary']['errors'] == 0, f'no harvester errors ({[k for k in stats if isinstance(stats[k], dict) and k != "summary"]})')

        # 6b. A probe event over the same area with a window in the past and no hashtag
        # requirement, so the Overpass path has to find real recent edits.
        probe = requests.post(f'{api}/events/', json={
            'title': 'E2E Harvest Probe', 'slug': 'e2e-harvest-probe', 'hashtag': 'E2EProbe',
            'description': 'temporary', 'bounding_polygon': event['bounding_polygon'],
            'start_time': '2026-06-01T00:00:00Z', 'end_time': '2027-01-01T00:00:00Z',
        }, timeout=10)
        if probe.status_code == 400:  # left over from an aborted run
            leftovers = requests.get(f'{api}/events/', timeout=10).json()['results']
            probe_id = next(e['id'] for e in leftovers if e['slug'] == 'e2e-harvest-probe')
        else:
            check(probe.status_code == 201, 'probe event created')
            probe_id = probe.json()['id']
        quest = requests.post(f'{api}/quests/', json={
            'event': probe_id, 'title': 'Probe: eateries with hours', 'description': 'temporary',
            'criteria_type': 'osm_tags', 'target_geometry': None, 'points_reward': 1,
            'validation_rules': {'required_tags': {'amenity': 'restaurant|cafe', 'opening_hours': '*'},
                                 'target_count': 1, 'require_hashtag': False},
        }, timeout=10)
        check(quest.status_code == 201, 'probe quest created')
        stats = harvest_dry_run(probe_id)
        check(stats is not None and stats.get('osm', {}).get('errors', 1) == 0, 'probe harvest ran without OSM errors')
        found = stats.get('osm', {}).get('harvested', 0)
        check(found > 0, f'Overpass found {found} recent eatery edits with opening_hours in downtown Sacramento')
        sample = next((w for w in stats.get('would_submit', []) if w['platform'] == 'osm'), None)
        check(sample is not None and sample.get('author') and sample.get('element_count', 0) >= 1,
              f'would-be submission carries author and element count ({sample})')
        requests.delete(f'{api}/events/{probe_id}/', timeout=10)
    else:
        print('  SKIP  OVERPASS_URL not set; run with OVERPASS_URL="$(cat ~/.overpassurl)" to include harvesting')

    if not args.keep:
        print('7. Cleanup')
        # Submissions survive the team delete (team is SET_NULL), so remove the ones we made.
        subs = requests.get(f'{api}/submissions/', params={'event': event_id}, timeout=10).json()
        subs = subs.get('results', subs)
        ours = [sub for sub in subs if str(sub.get('external_id', '')).startswith('e2e-')
                or sub.get('author_username') == 'E2E Smoke']
        for sub in ours:
            requests.delete(f'{api}/submissions/{sub["id"]}/', timeout=10)
        check(True, f'{len(ours)} e2e submissions removed')
        deleted = requests.delete(f'{api}/teams/{team_id}/', timeout=10)
        check(deleted.status_code == 204, 'throwaway team deleted')

    print(f'\nAll {PASSED} checks passed.')


if __name__ == '__main__':
    main()
