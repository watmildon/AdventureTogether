# AdventureTogether - FOSS4G NA 2026 Build Summary

- **Date & Time**: 2026-10-06, overnight session (started 2026-10-05 evening)
- **Branch**: `feature/foss4gna-2026-event` (not merged to main; review in the morning)
- **Task**: Implement the plan in `.junie/plans/foss4gna-2026-sample-event.md` so the app can run its first real event at FOSS4G North America 2026 in Sacramento (2-4 Nov 2026).

---

## 1. Input prompt and understanding

Matt asked for the whole plan to be implemented tonight, including the two quest types he wants to think about tomorrow (GPS check-in, GitHub contribution) so they can be cut rather than built later. OSM harvesting should use his private Overpass endpoint, with the secret delivered through the deployment rather than committed. Work was to be checked in in sensible chunks, orchestrated and reviewed by a Fable agent with Opus agents doing the coding, with end-to-end test scripts as appropriate.

## 2. How the work was organised

The Fable session wrote the briefs, reviewed every diff, ran the suites, and committed. Five Opus coding agents each took one chunk; three of them worked in isolated git worktrees so they could run in parallel without stepping on each other, and their branches were merged once reviewed. A code-review pass over the full branch diff then produced ten findings, which two further agents fixed. Commits on the branch, oldest first:

| Commit | Chunk |
|---|---|
| e21e9c2 | The plan itself |
| 6babdd2 | Data model and API contract: quest progress, session linkage, contributor usernames, deploy secret plumbing |
| 612cd92 | GPS check-in quests verified from location pings |
| ee7e3fc | `seed_event` command and the FOSS4G NA 2026 fixture (22 quests) |
| ee0afd9 | End-to-end smoke script |
| b9243e6 | Harvesters rebuilt on Overpass; OSM Notes, OpenHistoricalMap, Wikidata statement and GitHub sources; scheduling |
| f6ae1ec | Docs for check-ins, harvesters, scheduling; live harvest probe in the smoke script |
| bfa42ff | Frontend: quest panel, leaderboard, check-in feedback, builder for every quest type |
| (final) | Review fixes, see section 5 |

## 3. What was built

### Backend (`backend/`)
- **Quest model**: six new criteria types (`location_checkin`, `osm_notes`, `ohm_feature`, `wikidata_statement`, `oss_contribution`, `street_imagery`), `inspired_by` JSON describing the conference session behind a quest, optional `window_start`/`window_end`, and `target_count` read from `validation_rules`. The per-type `validation_rules` contract is in `documentation/quest_types.md`.
- **Scoring**: new `QuestProgress` (team x quest) and `services/progress.py`. Points are awarded once when a team's verified `element_count` reaches `target_count` and revoked if it drops below. The verify action uses it; a migration backfills rows for already-verified submissions so nothing double-awards.
- **Team membership** records optional OSM, Wikimedia and GitHub usernames, used to credit harvested contributions to teams.
- **Events** take a `schedule_url` (pretalx/frab JSON); `GET /api/events/{id}/sessions/` returns the flattened programme (cached 10 min). New `GET /api/events/{id}/leaderboard/` and `GET /api/teams/{id}/progress/`.
- **GPS check-ins** (`services/checkin.py`): a foreground ping within `radius_m` of a point target (or inside a polygon) during the quest window creates a `checkin` submission; after `min_minutes` in range it auto-verifies. The ping response reports in-range quests; `GET /api/locations/checkins/` lists a participant's check-ins. A host revocation is never overridden.
- **Harvesters** (`services/*_harvester.py`, `harvest_common.py`, `harvest_worker.py`): each `osm_tags` quest becomes one Overpass query (required tags, quest area, `newer:` since the event or quest window, `out meta`); results are grouped by changeset and the changeset's hashtag and time are confirmed through the OSM API. OpenHistoricalMap uses the same path against the public OHM Overpass. OSM Notes, Wikimedia Commons (real uploader, optional category), Wikidata (any edit, or a statement on a named item), and GitHub PRs/issues are harvested too. Only the platforms an event's active quests need are contacted; stats are per platform; errors are logged by exception class so endpoint URLs never leak. Without `OVERPASS_URL` the OSM harvester skips with a warning rather than using a public instance.
- **Scheduling**: `manage.py setup_schedules` registers Django-Q2 schedules (harvest every 5 min for events whose window is current, ping cleanup every 10 min). `manage.py harvest_event <id> [--dry-run]` runs one harvest by hand.
- **Seeding**: `manage.py seed_event fixtures/foss4gna_2026.json --schedule-json fixtures/foss4gna_2026_schedule.json` upserts the event, 22 quests and a demo team in one transaction, expanding code-only `inspired_by` entries from the schedule export. Idempotent.
- **Secrets**: `OVERPASS_URL` and `GITHUB_TOKEN` are read only from the environment. Both docker-compose files pass them through; the Ansible application role writes `deploy/.env` (mode 0600) from vaulted `group_vars`, with a tracked `.example` and the real file ignored. No secret value appears anywhere in the repo.

### Frontend (`frontend/`)
- Event map: quest panel with type, points, team progress, quest window, "Inspired by" session line with link, and Show on map; polygon targets drawn; leaderboard (polled); check-in banner and card state; the participant's own marker (previously never drawn); phone layout stacks the map above the sidebar.
- Join page collects the three contributor usernames.
- Host builder covers all nine quest types with per-type rule inputs, an optional window, and a session picker backed by `/sessions/`; existing quests can be deleted.
- Verification page shows new platforms, element counts and contribution times, with a team progress panel.

### Docs
`documentation/quest_types.md`, `harvesters.md`, `seeding_events.md` are new; `api_reference.md`, `user_guide.md`, `deployment_guide.md`, `local_setup.md` and `FEATURES.md` (FEAT-012 to FEAT-019) are updated.

## 4. Verification

- Backend: `pytest` on the final branch, 148 passing. Migration check clean.
- Frontend: `vitest` 74 passing; `npm run build` (vue-tsc) passing.
- `scripts/e2e_smoke.py` against the running dev server: 28 checks covering seeding, team join with usernames, a GPS check-in that auto-verifies and scores, a counted quest advancing through host verification and revocation, the leaderboard, a dry-run harvest of the seeded event on all six platforms with zero errors, and a live probe event over downtown Sacramento where the Overpass harvester found 7 real recent eatery edits with authors and element counts.
- Headless Chromium drove the real UI: joining the demo team, standing at the Capitol check-in via the simulated GPS override, seeing the banner, and the leaderboard moving to 10 points, with the backend confirming the verified check-in. Screenshots were inspected at 420 px and 1280 px.

## 5. Review findings and fixes

A code-review pass over the full branch diff produced ten findings. All were fixed in the final commit:
- Check-in status after a page reload treated every recorded check-in as verified (the endpoint returns `status`, not `is_verified`).
- A team joined for one event was used as the participant's team on another event's map.
- Blank usernames were dropped from the join payload, so a stored username could never be cleared.
- `schedule_url` let anyone make the server fetch an arbitrary URL; fetches are now limited to https hosts in `SCHEDULE_URL_ALLOWED_HOSTS` (default `talks.osgeo.org,pretalx.com`).
- Deleting a quest cascaded its progress rows without revoking the points on the team score; a pre-delete handler now settles scores.
- Smaller items: a duplicated haversine, repeated team-matching queries per contribution, a redundant membership query on check-in, dead `matches_osm_tags` code, and check-in list ordering.

## 6. Open items for the morning

Decisions from the plan's section 7 that are still Matt's call: the hashtag (`FOSS4GNA2026` is seeded), the perimeter, whether to keep check-in and GitHub quests, whether a GitHub token goes into the deployment, prizes and a public scoreboard, and quest 16 (new Wikidata item) which is seeded as `wikidata_entry` because there is no QID to target yet.

Not built: `street_imagery` (Panoramax) is seeded inactive; the builder pins points but cannot draw polygons or edit quests; quest windows are enforced server-side but only displayed client-side; there is still no authentication on any endpoint, which blocks a public deployment and should be the next piece of work; pagination beyond the first page of each external source.

Operational notes: run `manage.py setup_schedules` once per deployment after `migrate`; set `OVERPASS_URL` in the deployment environment (locally `export OVERPASS_URL="$(cat ~/.overpassurl)"`); the dev database already contains the seeded FOSS4G event as event 2.
