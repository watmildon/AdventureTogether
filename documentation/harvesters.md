# Harvesters

How AdventureTogether finds participants' open-data contributions on external platforms and turns them into submissions that hosts verify. For the quest types themselves and their `validation_rules`, see [quest_types.md](quest_types.md).

---

## 1. Overview

A harvest run takes one event and looks at its **active** quests. For each criteria type present it calls the matching harvester; a type with no active quests is never fetched (an event without `oss_contribution` quests never calls GitHub).

| Criteria type | Harvester module | Source | Submission `platform` |
|---|---|---|---|
| `osm_tags` | `overpass_harvester.py` | Overpass (`OVERPASS_URL`) + OSM changeset API | `osm` |
| `ohm_feature` | `overpass_harvester.py` | OHM Overpass (`OHM_OVERPASS_URL`) + OHM changeset API | `ohm` |
| `osm_notes` | `osm_notes_harvester.py` | OSM Notes API | `osm_notes` |
| `wikimedia_commons` | `wikimedia_harvester.py` | Commons MediaWiki API | `commons` |
| `wikidata_entry`, `wikidata_statement` | `wikidata_harvester.py` | Wikidata MediaWiki API | `wikidata` |
| `oss_contribution` | `github_harvester.py` | GitHub issue search API | `github` |
| `mangrove_review` | `mangrove_harvester.py` | Mangrove Reviews API (`MANGROVE_API`) | `mangrove` |
| `maproulette_task` | `maproulette_harvester.py` | MapRoulette API (`MAPROULETTE_API`) + OSM changeset API | `maproulette` |
| `location_checkin` | not harvested (verified from location pings) | | `checkin` |
| `street_imagery` | not implemented | | `panoramax` |

All modules live in `backend/apps/submissions/services/`; `harvest_worker.py` dispatches between them.

For every qualifying contribution a harvester creates one `Submission` per (contribution, quest) with:

- `author_username`: the account on the external platform,
- `team`: the team of the member who shared that username (see section 8),
- `contributed_at`: when the contribution happened on the platform,
- `element_count`: how many distinct things it adds toward a counted quest,
- `diff_payload`: the evidence a host reviews.

Submissions start unverified. A host verifies them, and the progress service adds the quest's points once the team's verified `element_count` reaches `target_count`.

A contribution only counts when it happened inside the event window (`start_time` to `end_time`) **and** inside the quest's own window when `window_start` / `window_end` are set.

### Re-harvesting

Harvests are idempotent. `(platform, external_id)` is unique, and external ids carry the quest id (`5001/q7`) wherever one contribution can satisfy several quests. On a later run an existing submission is updated when:

- more elements now match (e.g. an open OSM changeset gained edits): `element_count` and `diff_payload` are refreshed;
- its author can now be credited to a team (the participant added their username after editing).

If the submission is already verified, the team's quest progress is recomputed straight away, so counted quests advance without another host action.

---

## 2. OpenStreetMap: Overpass and changesets

The OSM harvester asks Overpass for the elements that **currently** carry the quest's tags, sit in the quest's area, and were last edited since the quest window opened. One query per `osm_tags` quest:

```
[out:json][timeout:60];
nwr["amenity"="cafe"]["opening_hours"](poly:"38.572 -121.509 38.590 -121.509 ...")(newer:"2026-11-02T16:00:00Z");
out meta center;
```

- Tags: `["k"="v"]`, `["k"]` for `"*"`, and `["k"~"^(a|b)$"]` for `"a|b"`.
- Area: a Point target becomes `(around:radius_m,lat,lon)`, a Polygon target `(poly:"lat lon ...")`, and no target the event's `bounding_polygon`.
- Time: `newer:` is the quest's `window_start`, or the event's `start_time`, in UTC.
- `out meta center` returns `user`, `uid`, `changeset`, `timestamp`, and `version` for each element, plus a centre point for ways and relations.

The request is a `POST` with `data=<query>`, an HTTP timeout of 90 s, and the harvest User-Agent.

The elements are then grouped by `changeset`. Each changeset's metadata (`user`, `created_at`, `closed_at`, `tags`) is fetched from `{OSM_API_BASE}/changeset/{id}.json` **once per run**. Closed changesets never change, so their metadata is also cached in the Django cache for 24 hours. This keeps the 5-minute schedule from re-fetching the same changesets.

A changeset qualifies for a quest when:

1. it carries the event hashtag (see 2.1), unless the quest sets `"require_hashtag": false`;
2. its `created_at` is inside the event window and the quest is open at that time.

The submission's `external_id` is `{changeset}/q{quest}`, `element_count` is the number of distinct matching elements, and `contributed_at` is `closed_at` (or `created_at` while the changeset is still open). `diff_payload` is:

```json
{
  "changeset": {"id": 5001, "user": "mapper_alice", "created_at": "2026-11-03T18:00:00Z",
                "comment": "Added opening hours", "hashtags": "#FOSS4GNA2026;#StreetComplete"},
  "elements": [
    {"type": "node", "id": 1001, "version": 7, "user": "mapper_alice",
     "timestamp": "2026-11-03T18:02:00Z", "lat": 38.5801, "lon": -121.4902,
     "tags": {"amenity": "cafe", "opening_hours": "Mo-Su 06:00-22:00"}}
  ]
}
```

**Limitation:** Overpass only reports the latest version of each element. If someone else edits an element after a participant, the element moves to the later changeset and the participant's changeset loses it on the next harvest. A submission's `element_count` never decreases, though, so credit that has already been harvested is kept. Quests that count newly created elements (`"action": "create"`, see 2.4) do not have this problem.

A quest with `"action": "modify"` drops elements whose current version is 1 before grouping, so only updates to elements that already existed count.

### 2.1 Changeset hashtag convention

Participants put the event hashtag in their changeset in either of two ways:

- the **`hashtags` changeset tag**, a semicolon-separated list written by iD, StreetComplete, Every Door, and others (e.g. `#FOSS4GNA2026;#StreetComplete`). The leading `#` is optional there;
- the **changeset comment**, containing `#FOSS4GNA2026`.

Matching is case-insensitive and on whole tokens: `#FOSS4GNA2026hunt` does **not** match `FOSS4GNA2026`. The same `hashtag_matches` helper (in `tag_matcher.py`) checks note comments, Wikimedia edit summaries, and GitHub titles and bodies.

### 2.2 The Overpass endpoint (`OVERPASS_URL`)

The OSM harvester sends every query to `settings.OVERPASS_URL`, which is read from the environment. Our deployment uses a private Overpass instance, so treat the value as a **secret**:

- Set it only in the environment (e.g. `export OVERPASS_URL="$(cat ~/.overpassurl)"`), never in committed files.
- The harvesters never log it. Errors are reported by exception class and HTTP status only, because `requests` puts the URL in its exception messages.
- If `OVERPASS_URL` is empty, `osm_tags` quests are **skipped**: the run logs a warning and adds it to the stats' `warnings`. There is deliberately no fallback to a public instance, because public Overpass servers rate-limit hard. For local experiments you can point it at a public server yourself, e.g. `OVERPASS_URL=https://overpass-api.de/api/interpreter`.

The endpoint must support `newer:` and `out meta`; any standard Overpass API does.

### 2.3 OpenHistoricalMap

`ohm_feature` quests use the same code path with different endpoints:

| | OSM | OHM |
|---|---|---|
| Overpass | `OVERPASS_URL` (secret, required) | `OHM_OVERPASS_URL` (public, default `https://overpass-api.openhistoricalmap.org/api/interpreter`) |
| Changeset API | `OSM_API_BASE` | `OHM_API_BASE` |
| Submission URL | `https://www.openstreetmap.org/changeset/{id}` | `https://www.openhistoricalmap.org/changeset/{id}` |
| Default `required_tags` | none | `{"start_date": "*"}` |

### 2.4 New elements: history lookups

A quest with `"action": "create"` credits the user and changeset that **created** each element, so it needs the element's version 1, which Overpass does not return once the element has been edited. The Overpass query is the same (an element created in the window was necessarily last edited in it too); then, per distinct element:

1. **Current version 1:** the element's own `user`, `changeset` and `timestamp` are its creation. No extra call.
2. **Version above 1, already tracked for this quest, and the version is not above `last_seen_version`:** the stored creation info is reused. No extra call.
3. **Otherwise** (unknown element, or its version has gone up): one `GET {OSM_API_BASE}/{type}/{id}/history.json`, and version 1's `user`, `changeset` and `timestamp` are taken from it. The same element is fetched at most once per run, however many quests match it.

What the harvester learns is stored in `TrackedOsmElement` (one row per quest and element): `last_seen_version`, `created_at_osm`, `creator_username`, `creation_changeset`, `last_editor_username` and `last_checked`. The version and last editor are refreshed on every run. A dry run may still call the history API but writes no rows.

The element qualifies when `created_at_osm` is inside the event window and the quest window, and the creating changeset carries the hashtag (checked with the same cached changeset lookup, and skipped when `require_hashtag` is `false`). Qualifying elements are grouped by creating changeset into one submission each (`{changeset}/q{quest}`), credited to the creator, with `contributed_at` the creation time and `element_count` the number of elements that changeset created. Each element in `diff_payload` carries version 1's `version`, `user` and `timestamp`, plus `current_version`.

So the first run after a participant adds ten hydrants costs nothing extra (they are all at version 1). Each later edit by anyone costs one history call on the next run, and nothing after that until the element changes again. The count is reported as `history_lookups` in the platform's stats (section 9). A failed lookup is counted under `errors`, writes no row, and is retried on the next run.

An element that is deleted after being created no longer appears in Overpass, so it stops counting toward new submissions; credit already harvested is kept.

---

## 3. OSM Notes

`GET {OSM_API_BASE}/notes.json?bbox=<event bbox>&closed=-1&limit=100` returns open and closed notes in the bounding box of the event perimeter, newest first. A note qualifies when:

- `status` is `closed` and `closed_at` is inside the event window and the quest's window;
- at least one comment contains the hashtag;
- it lies in the quest's area: within `radius_m` (default 300) of a Point target, inside a Polygon target, or inside the event perimeter.

The author is the user who closed the note. If the note was closed anonymously, the author is the user who wrote the hashtag comment. A note produces one submission per matching quest (`{note}/q{quest}`) with `diff_payload = {status, comments}`.

---

## 4. Wikimedia Commons and Wikidata

**Commons.** A full-text search in the File namespace (`list=search&srnamespace=6&srsearch=#TAG`) finds files whose description mentions the hashtag. The harvester then resolves each hit with `prop=imageinfo|categories&iiprop=user|timestamp|url|extmetadata` (`iiextmetadatafilter=ImageDescription|ObjectName`, so the file's description and object name land in `diff_payload` as plain text for value-scoring quests). The uploader (`imageinfo.user`) is the author, the upload time must fall in the window, and the file's description page is the submission URL. When a quest sets `category`, the file must be in that category. Each (file, quest) pair is one submission. On a quest with `validation_rules.scoring.value`, every platform's submissions get `extracted_value` read from their payload at harvest time (see `quest_types.md`, Value scoring).

**Wikidata, `wikidata_entry`.** Candidate edits come from two sources:

- a hashtag search of items, whose revisions in the window are then read with `prop=revisions&rvlimit=20`;
- the in-window contributions (`list=usercontribs`) of every team member who shared a `wikimedia_username`.

Wikidata's search does not index edit summaries, so the second source is what finds most edits in practice. Every revision whose summary contains the hashtag becomes one submission (`external_id` = revision id), assigned to the first open `wikidata_entry` quest.

**Wikidata, `wikidata_statement`.** For each quest the harvester reads up to 100 revisions of the named item (`validation_rules.qid`) inside the quest window. It keeps those whose summary has the hashtag **and** mentions one of the configured properties as a whole token. Wikidata's automatic summaries contain e.g. `[[Property:P84]]`, and `P84` does not match `P8410`.

---

## 5. GitHub

The harvester runs one search per kind requested by any quest:

```
GET https://api.github.com/search/issues?q="#TAG" in:body,title is:pr created:>=YYYY-MM-DD
GET https://api.github.com/search/issues?q="#TAG" in:body,title is:issue created:>=YYYY-MM-DD
```

Results are re-checked locally: the hashtag must be a token in the title or body, `created_at` must be in the window, and, when `allowed_owners` is set, the repository owner must be in it (case-insensitive). Requests send `Accept: application/vnd.github+json` and, when `GITHUB_TOKEN` is set, `Authorization: Bearer <token>`.

Without a token GitHub allows 10 search requests a minute. The harvester logs that once per worker process and keeps going. A 403 or 429 is counted as an error, and the next run retries.

---

## 6. Mangrove Reviews

[Mangrove](https://mangrove.reviews) is an open dataset of reviews signed with each reviewer's own key; nobody needs an account. One request per run covers every `mangrove_review` quest:

```
GET {MANGROVE_API}/geo?xmin=<min lon>&ymin=<min lat>&xmax=<max lon>&ymax=<max lat>
```

The box is the union of the quests' areas: the extent of a Polygon target, a box of `radius_m` around a Point target, or the event perimeter's extent. The response is `{"reviews": [...]}`, each with `signature`, `jwt`, `kid` (the reviewer's public key) and usually `payload`. When `payload` is missing it is read from the JWT's middle segment; the signature is not checked, since we only read what the reviewer published. A review qualifies for a quest when:

- its subject is a place (`geo:lat,lon?q=Name&u=30`, falling back to the `geo.coordinates` the API adds) inside the quest's area;
- `iat` (unix seconds) is inside the event window and the quest's window;
- the opinion contains the hashtag (unless `require_hashtag` is false), has at least `min_opinion_chars` characters and, when `min_rating` is set, the rating is at least that.

Each (review, quest) pair is one submission: `external_id` `{signature}/q{quest}` (a signature too long for the column is replaced by its SHA-256), linked to `https://mangrove.reviews/list?signature=...`, with `diff_payload` `{sub, place, rating, opinion, text, nickname, osm_id, client_id, lat, lon}` (`text` repeats the opinion so value scoring's `description` source can read it). The author is the review's `metadata.nickname`; reviews without one are attributed to `anonymous key <first 12 hex of sha256(kid)>`. See section 8 for how nicknames are matched.

---

## 7. MapRoulette

[MapRoulette](https://maproulette.org) serves challenges: lists of small OSM fixes, one task per spot. MapRoulette accounts are OSM logins. For all `maproulette_task` quests together the harvester lists the tasks in the union of their areas' boxes:

```
GET {MAPROULETTE_API}/tasks/box/{left}/{bottom}/{right}/{top}?limit=200&page=N&tStatus=1,5
```

Two behaviours of this endpoint, checked against maproulette.org:

- Without `tStatus` the listing leaves fixed tasks out, so the harvester always passes the union of the quests' `statuses`.
- Each item's `modified` is the time of the response, not of the task. Completed tasks carry `mappedOn` and `completedBy` (`{id, username}`) in the listing, so the window is judged from `mappedOn`.

Pages are 0-based; the harvester keeps paging while a page comes back full (200 items) and stops after 20 pages with a warning. A listed task is kept for a quest when its `status` is in the quest's `statuses`, its point is in the quest's area, its `parentId` (challenge) is in `challenge_ids` when that is set, and its `mappedOn`, when listed, is in the window.

Each kept task is then fetched once, `GET {MAPROULETTE_API}/task/{id}`, for `changesetId`, `completedBy`, `mappedOn`, `modified` and `parent`. These requests are counted in the `detail_lookups` stat. A task whose stored submission for the quest has the same `status` and `mappedOn` as the listing (or the same `modified` when the listing has no `mappedOn`) is not fetched again; the stored submission is re-offered so a team can still be filled in.

Attribution, in order:

1. `changesetId > 0`: the OSM changeset's metadata (the same cached lookup as section 2) gives the OSM username and lets `require_hashtag` be checked. MapRoulette records `-1` when it does not know the changeset, which is common.
2. Otherwise the user who completed the task: the username in the listing's `completedBy`, or, if the listing has none, `GET {MAPROULETTE_API}/user/{id}/public`, whose `osmProfile.displayName` is the OSM name (`name` is the fallback).
3. Otherwise the author is `MapRoulette user <id>`. A task with no `completedBy` at all is skipped.

A quest with `require_hashtag: true` only credits tasks whose changeset is known and carries the hashtag. Each (task, quest) pair is one submission, `external_id` `{task}/q{quest}`, linked to `https://maproulette.org/challenge/{challenge}/task/{task}`, `contributed_at` = `mappedOn` (or `modified`), with `diff_payload` `{challenge_id, challenge_name, task_title, status, changeset_id, mapped_on, modified, completed_by, attributed_by}`.

---

## 8. Crediting contributors to teams

`match_author_to_team(event, author_username, platform)` compares the author with the event's team members, case-insensitively, in this order:

1. the platform username a member shared when joining: `osm_username` for `osm`, `osm_notes`, `ohm` and `maproulette`; `wikimedia_username` for `commons` and `wikidata`; `github_username` for `github`;
2. the member's `user_identifier`;
3. the member's `display_name`.

For `mangrove` there is no username field: the author is the nickname the reviewer chose, so `display_name` is tried first and then `user_identifier`. Participants should set their Mangrove nickname to their display name in the hunt.

Submissions with no matching member are still stored (`team = null`). If the member adds their username later, the next harvest fills the team in.

Within one run each `(platform, author)` pair is matched once and the result (including "no team") is reused for that author's other contributions; a submission that already has a team is not matched again.

---

## 9. Running harvests

### Scheduled (production)

```bash
python manage.py setup_schedules   # idempotent; run on every deploy
python manage.py qcluster          # the Django-Q2 worker
```

`setup_schedules` creates or updates two Django-Q2 `Schedule` rows (type MINUTES, repeat forever):

| Name | Function | Every |
|---|---|---|
| `harvest_all_active_events` | `apps.submissions.services.harvest_worker.harvest_all_active_events` | 5 min |
| `cleanup_expired_pings` | `apps.locations.views.cleanup_expired_pings` | 10 min |

`harvest_all_active_events` harvests only active events whose window, padded by one day on each side, contains the current time.

`Q_CLUSTER` uses a 300 s task timeout and a 360 s retry. One run makes several external calls, and the retry must be longer than the timeout or the ORM broker re-delivers tasks that are still running.

### By hand

```bash
python manage.py harvest_event 1            # harvest event 1 and print the stats as JSON
python manage.py harvest_event 1 --dry-run  # make every fetch, write nothing, list would-be submissions
```

`POST /api/submissions/trigger_harvest/` with `{"event": 1}` runs the same harvest inside the request and returns the stats.

### Stats shape

```json
{
  "event": 1,
  "found": true,
  "dry_run": false,
  "osm":       {"harvested": 3, "created": 1, "updated": 1, "matched": 2, "errors": 0, "history_lookups": 2},
  "osm_notes": {"harvested": 1, "created": 1, "updated": 0, "matched": 0, "errors": 0},
  "github":    {"harvested": 0, "created": 0, "updated": 0, "matched": 0, "errors": 1},
  "maproulette": {"harvested": 2, "created": 1, "updated": 0, "matched": 1, "errors": 0, "detail_lookups": 1},
  "summary":   {"harvested": 4, "created": 2, "updated": 1, "matched": 2, "errors": 1},
  "warnings":  []
}
```

- `harvested`: qualifying (contribution, quest) pairs found, including ones already stored.
- `created` / `updated`: submissions written. In a dry run, the number that would have been written.
- `matched`: created or updated submissions that were credited to a team.
- `errors`: failed external calls. A failure in one platform never stops the others.
- `history_lookups` (`osm` and `ohm` only): element history requests made for `"action": "create"` quests (section 2.4). It is not added to `summary`.
- `detail_lookups` (`maproulette` only): `GET /task/{id}` requests (section 7). It is not added to `summary`.
- `warnings`: non-error conditions, e.g. `OVERPASS_URL is not configured; skipped osm_tags quests`.

Only platforms that ran appear as keys. A dry run adds `"would_submit": [{"platform", "external_id", "author", "element_count", "quest", "team", "action"}]`.

---

## 10. Etiquette and limits

- Every request sends `HARVEST_USER_AGENT`, a descriptive User-Agent as the OSM and Wikimedia API policies require. Override it per deployment with a contact address.
- Every request has a timeout: 30 s for REST APIs, 90 s HTTP and `[timeout:60]` server-side for Overpass.
- Queries are bounded: Overpass by area, `newer:`, and tags; Notes by bbox and `limit=100`; MediaWiki searches by `srlimit=50`; revisions by `rvstart`/`rvend` and `rvlimit`; GitHub by `created:>=` and `per_page=100`; Mangrove by one bbox request per run; MapRoulette by bbox, `tStatus`, `limit=200` and at most 20 pages.
- Mangrove and MapRoulette publish no rate limits and need no authentication. Each run makes one Mangrove request, and for MapRoulette one listing request per page plus one task request per new or changed qualifying task (and a profile request only when the listing lacks the completing user's name). Do not list a challenge's tasks (`/challenge/{id}/tasks`): those listings are slow and can time out; the bbox listing is what the harvester uses.
- OSM changeset metadata is fetched once per run and cached for 24 h once the changeset is closed.
- Element history is fetched only for `"action": "create"` quests, at most once per element per run, and again only when the element's version goes up (section 2.4). Watch `history_lookups` in the stats.
- On a 5-minute schedule an event with N `osm_tags` quests makes N Overpass queries per run. Keep N modest, or lengthen the schedule interval for very large events.
