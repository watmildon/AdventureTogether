# Seeding Events from a File

`manage.py seed_event` creates or updates an event, its quests and (optionally) teams from one JSON file. Use it to set up a real event ahead of time, keep the quest set in version control, and re-apply edits without clicking through the host UI.

The first real seed file is the FOSS4G NA 2026 hunt in [`backend/fixtures/foss4gna_2026.json`](../backend/fixtures/foss4gna_2026.json). The plan behind it is `.junie/plans/foss4gna-2026-sample-event.md`.

---

## 1. The command

```bash
python manage.py seed_event <path.json> [--schedule-json <schedule.json>] [--replace-quests]
```

| Option | Effect |
|---|---|
| `path.json` | The seed file (format below). |
| `--schedule-json PATH` | A local pretalx/frab schedule export used to expand `inspired_by` codes. Without it, the event's `schedule_url` is fetched over the network. |
| `--replace-quests` | Delete the event's quests whose titles are not in the file. Without it, extra quests are left alone. |

Behaviour:

- **Upsert, not insert.** The event is matched by `slug`, quests by `(event, title)`, teams by `(event, name)`. Running the same file twice changes nothing the second time; the summary reports everything as `unchanged`. Rename a quest and it is treated as a new quest (and the old one is only removed with `--replace-quests`).
- **All or nothing.** The whole file is validated first, and the writes run in one transaction, so a bad file leaves the database exactly as it was.
- **Validation.** Every geometry must be valid GeoJSON; the event polygon must be a `Polygon`; every quest `target_geometry` must intersect the event polygon (the same rule as the quest API); `criteria_type` must be a known type; datetimes must be ISO 8601 with a UTC offset; `window_end` must not be before `window_start`; quest titles and team names must be unique within the file.
- **Deleting quests** with `--replace-quests` keeps existing submissions (their quest link becomes empty) but removes the deleted quest's team progress rows.
- **Summary.** The command prints whether the event was created, updated or unchanged; quests created / updated / unchanged / deleted (with titles); each team's join code; and any warnings.

---

## 2. File format

```json
{
  "event": {
    "title": "FOSS4G NA 2026 Open Data Hunt",
    "slug": "foss4gna-2026",
    "description": "Walk downtown Sacramento between sessions ...",
    "hashtag": "FOSS4GNA2026",
    "bounding_polygon": {"type": "Polygon", "coordinates": [[[-121.509, 38.572], [-121.481, 38.572], [-121.481, 38.59], [-121.509, 38.59], [-121.509, 38.572]]]},
    "start_time": "2026-11-02T08:00:00-08:00",
    "end_time": "2026-11-04T18:00:00-08:00",
    "is_active": true,
    "schedule_url": "https://talks.osgeo.org/foss4g-na-2026/schedule/export/schedule.json"
  },
  "quests": [
    {
      "title": "Shade the grid",
      "description": "Map ten street trees ... Put #FOSS4GNA2026 in the changeset comment ...",
      "criteria_type": "osm_tags",
      "validation_rules": {"required_tags": {"natural": "tree", "leaf_type": "*"}, "target_count": 10, "require_hashtag": true},
      "target_geometry": {"type": "Polygon", "coordinates": [[...]]},
      "points_reward": 40,
      "is_active": true,
      "window_start": null,
      "window_end": null,
      "inspired_by": {"code": "ZDHDHP"}
    }
  ],
  "teams": [
    {"name": "Organisers (demo)"},
    {"name": "Judges", "join_code": "JUDGE1"}
  ]
}
```

### `event`

| Field | Required | Notes |
|---|---|---|
| `title` | yes | |
| `slug` | no | The upsert key. Defaults to the slugified title; set it explicitly so renaming the event does not create a second one. |
| `description` | no | |
| `hashtag` | yes | Leading `#` is stripped. |
| `bounding_polygon` | yes | GeoJSON `Polygon`, lon/lat order, closed ring, EPSG:4326. |
| `start_time`, `end_time` | yes | ISO 8601 with offset. |
| `is_active` | no | Default `true`. |
| `schedule_url` | no | pretalx/frab JSON export; used for `inspired_by` expansion and `GET /api/events/<id>/sessions/`. |

### `quests[]`

| Field | Required | Notes |
|---|---|---|
| `title` | yes | Upsert key within the event. |
| `description` | no | Participant-facing instructions. Say which app helps and that the hashtag goes in the changeset / upload comment. |
| `criteria_type` | no | Default `osm_tags`. One of `osm_tags`, `wikimedia_commons`, `wikidata_entry`, `location_checkin`, `osm_notes`, `ohm_feature`, `wikidata_statement`, `oss_contribution`, `street_imagery`. |
| `validation_rules` | no | Object; shape depends on the type (see below). |
| `target_geometry` | no | Any GeoJSON geometry, or `null` for "anywhere in the event perimeter". Must intersect the event polygon. |
| `points_reward` | no | Integer, default 10. |
| `is_active` | no | Default `true`. |
| `window_start`, `window_end` | no | Optional quest-specific window inside the event, e.g. a Monday-evening check-in. |
| `inspired_by` | no | `null`, a full session object, or `{"code": "..."}` to expand from the schedule (section 3). |

`validation_rules` used by the FOSS4G NA 2026 fixture:

| Type | Rules |
|---|---|
| `osm_tags` | `{"required_tags": {"key": "value" or "*"}, "target_count": n, "radius_m": 300, "require_hashtag": true}`; `radius_m` only when the target is a Point |
| `wikimedia_commons` | `{"category": "optional Commons category", "target_count": n}` |
| `wikidata_entry` | `{"target_count": n}` |
| `wikidata_statement` | `{"qid": "Q111393295", "properties": ["P84", "P571"], "target_count": 1}` |
| `osm_notes` | `{"target_count": n}` |
| `ohm_feature` | `{"required_tags": {"start_date": "*"}, "target_count": n}` |
| `oss_contribution` | `{"kinds": ["pr", "issue"], "allowed_owners": ["OSGeo", "qgis", ...], "target_count": 1}` |
| `location_checkin` | `{"radius_m": 60, "min_minutes": 0}` |
| `street_imagery` | `{"target_count": 1}` (stretch; not harvested yet) |

`required_tags` values are matched exactly (case-insensitive) or with `*` for "any value". There is no "a or b" syntax, so "restaurant or cafe" is written as `"amenity": "*"` inside a tight polygon.

### `teams[]` (optional)

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Upsert key within the event. |
| `join_code` | no | Generated when omitted and never changed on re-runs. If given it must not be used by any other team. |

---

## 3. `inspired_by` expansion

Quests can point at the conference session that inspired them. Writing the full object by hand is tedious and goes stale when the programme moves, so the seed file can carry only the pretalx talk code:

```json
"inspired_by": {"code": "78PVFZ"}
```

When at least one quest has a code-only `inspired_by`, the command loads the schedule:

1. from `--schedule-json` if given (works offline), otherwise
2. by fetching the event's `schedule_url` (from the file, or the existing event if the file omits it).

Each code is replaced with the matching session:

```json
{
  "code": "78PVFZ",
  "title": "OpenHistoricalMap: across the geoverse",
  "speakers": ["Minh Nguyễn"],
  "start": "2026-11-04T11:00:00-08:00",
  "room": "Beavis",
  "track": "Community of Practice",
  "url": "https://talks.osgeo.org/foss4g-na-2026/talk/78PVFZ/"
}
```

If no schedule is available (no `--schedule-json`, no `schedule_url`, or the fetch fails) the code-only objects are stored as they are and a warning lists the affected quest titles. A code that is not in the schedule is also stored as-is with a warning. Re-run the command later with a schedule to fill them in.

An `inspired_by` object with any key besides `code` is stored exactly as written. Use that for things that are not talks, e.g. social events:

```json
"inspired_by": {"title": "Welcome Icebreaker BBQ", "speakers": [], "start": "2026-11-02T18:00:00-08:00",
                "room": "Sheraton Grand Sacramento", "track": "Conference Events",
                "url": "https://www.foss4gna.org/conference-events"}
```

To find codes, open the schedule on pretalx (the code is the last part of a talk URL, `/talk/78PVFZ/`) or call `GET /api/events/<id>/sessions/` on an event that has a `schedule_url`.

---

## 4. Seeding FOSS4G NA 2026

The repo ships the event file and a snapshot of the pretalx export (127 sessions) so seeding works offline:

- `backend/fixtures/foss4gna_2026.json`: event, 24 quests, one demo team
- `backend/fixtures/foss4gna_2026_schedule.json`: schedule export from `https://talks.osgeo.org/foss4g-na-2026/schedule/export/schedule.json`

Native (from `backend/`, with the virtualenv active and migrations applied):

```bash
python manage.py seed_event fixtures/foss4gna_2026.json \
    --schedule-json fixtures/foss4gna_2026_schedule.json
```

Docker Compose:

```bash
docker compose exec backend python manage.py seed_event fixtures/foss4gna_2026.json --schedule-json fixtures/foss4gna_2026_schedule.json
```

Drop `--schedule-json` to pull the live programme instead. Once the programme stops changing, refresh the snapshot by downloading the export over `fixtures/foss4gna_2026_schedule.json` and re-running the command; changed session times or rooms show up as `updated` quests.

The fixture's quests follow section 5 of the plan, with two of the plan's quests split in two because each quest has a single criteria type: "Memorial roll call" (Commons photos + OSM `image=` links) and "Old Sac" (Pony Express check-in + Judah Monument photo). "Street view, open" is seeded inactive because the `street_imagery` harvester does not exist yet.

**Open question: the hashtag.** The fixture uses `FOSS4GNA2026`, which the conference will probably also use on social media. OSM and OHM matches are limited to the event perimeter, but Commons and Wikidata searches are global, so unrelated edits could match. A hunt-specific tag such as `FOSS4GNA2026hunt` would avoid that. This is open question 1 in the plan. To switch, change `event.hashtag` and the `#FOSS4GNA2026` mentions in the quest descriptions, then re-run the command.
