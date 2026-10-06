# AdventureTogether - Developer API Reference

## Architectural Overview
AdventureTogether is built using **Django 5**, **GeoDjango**, **Django REST Framework (DRF)**, **PostgreSQL/PostGIS**, and **django-q2**. It exposes RESTful JSON and GeoJSON APIs.

- **Base Endpoint**: `/api/`
- **Spatial Reference System**: EPSG:4326 (WGS 84, Longitude / Latitude)
- **Task Broker**: PostgreSQL ORM via `django-q2` (Zero-Redis stack)

---

## 1. System & Health

### `GET /api/health/`
Returns current API status and active database engine.

**Response (200 OK)**:
```json
{
  "status": "healthy",
  "service": "AdventureTogether Backend API",
  "database_connected": true,
  "database_engine": "django.contrib.gis.db.backends.postgis",
  "version": "1.0.0"
}
```

---

## 2. Events API (`/api/events/`)

### `GET /api/events/`
Lists all scavenger hunt events.
- Query Parameters: `format=geojson` (optional, returns FeatureCollection)

### `POST /api/events/`
Creates a new scavenger hunt event.

**Payload**:
```json
{
  "title": "Mission District Hunt",
  "description": "Map amenities in the Mission.",
  "hashtag": "MissionHunt2026",
  "bounding_polygon": {
    "type": "Polygon",
    "coordinates": [[
      [-122.43, 37.76],
      [-122.40, 37.76],
      [-122.40, 37.79],
      [-122.43, 37.79],
      [-122.43, 37.76]
    ]]
  },
  "start_time": "2026-10-04T12:00:00Z",
  "end_time": "2026-10-04T18:00:00Z",
  "schedule_url": "https://talks.osgeo.org/foss4g-na-2026/schedule/export/schedule.json"
}
```

`schedule_url` is optional: a pretalx/frab-compatible schedule JSON export used by the sessions endpoint below.

### `GET /api/events/<id>/geojson/`
Returns the event bounding perimeter formatted as a GeoJSON Feature.

### `GET /api/events/<id>/leaderboard/`
Teams of the event ranked by `score` (descending), ties broken by `name`. Not paginated.
`completed_quests` counts the team's quests whose progress has reached `target_count`.

**Response (200 OK)**:
```json
[
  {"id": 3, "name": "Alpha", "score": 65, "member_count": 4, "completed_quests": 2},
  {"id": 1, "name": "Zeta", "score": 65, "member_count": 2, "completed_quests": 3},
  {"id": 2, "name": "Beta", "score": 10, "member_count": 3, "completed_quests": 1}
]
```

### `GET /api/events/<id>/sessions/`
Fetches the event's `schedule_url` (pretalx/frab JSON, `schedule.conference.days[].rooms{room: [talk]}`) and returns its talks as a flat list sorted by start time, in the same shape as a quest's `inspired_by` plus `type`. `start` is the talk's full ISO 8601 `date`. Results are cached for 10 minutes per URL.

**Response (200 OK)**:
```json
[
  {
    "code": "GDAL01",
    "title": "Code is liability",
    "speakers": ["Howard Butler"],
    "start": "2026-11-03T11:00:00-08:00",
    "room": "Ballroom A",
    "track": null,
    "url": "https://talks.osgeo.org/foss4g-na-2026/talk/GDAL01/",
    "type": "Talk"
  }
]
```

**Errors**: `400` if the event has no `schedule_url`; `502` if the schedule cannot be fetched or is not frab-shaped.

---

## 3. Teams API (`/api/teams/`)

### `GET /api/teams/?event=<event_id>`
Lists teams registered for an event with member counts and current scores.

### `POST /api/teams/`
Creates a new team. Automatically generates a unique 6-character `join_code`.

**Payload**:
```json
{
  "event": 1,
  "name": "Urban Explorers"
}
```

### `POST /api/teams/join/`
Allows a participant to join a team via join code. Creating a team is `POST /api/teams/` followed by this call with the new `join_code`, so both paths accept the platform usernames.

**Payload**:
```json
{
  "join_code": "EXPLOR42",
  "user_identifier": "device-uuid-12345",
  "display_name": "Alice",
  "osm_username": "alice_osm",
  "wikimedia_username": "Alice (WMF)",
  "github_username": "alice-gh"
}
```

`osm_username`, `wikimedia_username`, and `github_username` are optional. They let the harvesters credit contributions to the right team (the OSM name is also used for OpenHistoricalMap). A leading `@` is stripped. On re-join, a username field that is omitted keeps its stored value; an empty string clears it. All three are returned on each membership in `membership` and in the team's `memberships` roster.

### `GET /api/teams/<id>/progress/`
The team's progress on every quest of its event, ordered by quest title. Quests the team has not started appear with `count: 0` (no database rows are created for them).

**Response (200 OK)**:
```json
[
  {
    "quest": 4,
    "quest_title": "Farm-to-fork hours",
    "count": 3,
    "target_count": 5,
    "points_reward": 40,
    "completed_at": null,
    "points_awarded": false
  },
  {
    "quest": 5,
    "quest_title": "Icebreaker check-in",
    "count": 1,
    "target_count": 1,
    "points_reward": 10,
    "completed_at": "2026-11-03T02:14:09Z",
    "points_awarded": true
  }
]
```

---

## 4. Quests API (`/api/quests/`)

### `GET /api/quests/?event=<event_id>`
Lists active quests for an event. Supports `format=geojson`.

### `POST /api/quests/`
Creates a new quest. Rejects target geometries outside the event's bounding perimeter.

**Payload**:
```json
{
  "event": 1,
  "title": "Map Restaurant Opening Hours",
  "description": "Add opening_hours tag to 5 restaurants.",
  "criteria_type": "osm_tags",
  "validation_rules": {
    "required_tags": {
      "amenity": "restaurant",
      "opening_hours": "*"
    },
    "target_count": 5
  },
  "target_geometry": {
    "type": "Point",
    "coordinates": [-122.4194, 37.7749]
  },
  "points_reward": 20,
  "inspired_by": {
    "code": "ABC123",
    "title": "Farm-to-fork data",
    "speakers": ["Jane Mapper"],
    "start": "2026-11-03T16:00:00-08:00",
    "room": "Ballroom A",
    "track": "Community",
    "url": "https://talks.osgeo.org/foss4g-na-2026/talk/ABC123/"
  },
  "window_start": "2026-11-03T02:00:00Z",
  "window_end": "2026-11-03T04:00:00Z"
}
```

**Fields**:
- `criteria_type`: one of `osm_tags`, `wikimedia_commons`, `wikidata_entry`, `location_checkin`, `osm_notes`, `ohm_feature`, `wikidata_statement`, `oss_contribution`, `street_imagery`.
- `inspired_by` (optional object, default `{}`): the conference session behind the quest, in the shape returned by `GET /api/events/<id>/sessions/` (minus `type`). Must be a JSON object.
- `window_start` / `window_end` (optional, nullable): a quest-specific time window inside the event window, e.g. a Monday-evening-only check-in. `window_end` must not precede `window_start`.
- `target_count` (read-only in responses): number of verified contributions needed to complete the quest, taken from `validation_rules.target_count` (minimum and default 1).

---

## 5. Location Sharing API (`/api/locations/`)

### `POST /api/locations/ping/`
Ingests an ephemeral foreground location ping.

**Payload**:
```json
{
  "event": 1,
  "user_identifier": "device-uuid-12345",
  "display_name": "Alice",
  "longitude": -122.4194,
  "latitude": 37.7749,
  "visibility": "team",
  "is_foreground": true
}
```

### `GET /api/locations/checkins/?event=<event_id>&user_identifier=<user_id>`
Lists the participant's GPS check-in submissions for the event: `[{quest, quest_title, status: "verified"|"pending"|"revoked", first_seen, last_seen, ping_count, distance_m, radius_m, min_minutes, verified_at}]`. Both parameters are required (400 otherwise). The ping endpoint above also returns a `checkins` list (`[{quest, quest_title, status: "in_range"|"verified", distance_m}]`) for the quests the ping was in range of. See `documentation/quest_types.md`.

### `GET /api/locations/active/?event=<event_id>&user_identifier=<user_id>`
Returns active participant locations within the **20-minute decay window**, filtered according to privacy matrix permissions (`nobody`, `team`, `quest`).

---

## 6. Submissions & Verification API (`/api/submissions/`)

### `GET /api/submissions/?event=<event_id>&is_verified=<bool>&quest=<quest_id>`
Lists submissions harvested from OSM, Wikimedia Commons, or Wikidata.

`platform` is one of `osm`, `commons`, `wikidata`, `ohm`, `osm_notes`, `checkin`, `github`, `panoramax` (`platform_display` gives the human-readable name). Each submission also carries:
- `element_count` (default 1): how many distinct contributions it represents toward a counted quest, e.g. 3 cafes given `opening_hours` in one changeset.
- `contributed_at` (nullable): when the contribution happened on the external platform; `created_at` is when it was harvested.

### `POST /api/submissions/<id>/verify/`
Host endpoint to verify (or, with `"is_verified": false`, un-verify) a submission. After the change the team's progress on the quest is recomputed: progress `count` is the sum of `element_count` over the team's verified submissions for that quest. The quest's `points_reward` is added to the team score once, when `count` first reaches `target_count`, and removed again (score floored at 0) if revocations take it back below the target. Re-verifying an already verified submission does not award points twice.

**Payload**:
```json
{
  "is_verified": true,
  "verified_by_username": "HostMaster"
}
```

### `POST /api/submissions/trigger_harvest/`
Runs a harvest synchronously for the event and returns `{"message", "stats"}`. `stats` holds one `{harvested, created, updated, matched, errors}` entry per platform that ran (`osm`, `ohm`, `osm_notes`, `commons`, `wikidata`, `github`), plus `summary` (totals), `warnings`, `event`, `found` and `dry_run`. Returns 400 if `event` is missing or not an integer, and 404 (with `stats`) if the event does not exist or is inactive. Only the platforms the event's active quests need are contacted. See `documentation/harvesters.md`.

**Payload**:
```json
{
  "event": 1
}
```
