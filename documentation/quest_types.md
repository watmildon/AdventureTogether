# Quest Types

Every quest has a `criteria_type` that decides how it is verified, and a `validation_rules` JSON object whose keys depend on that type. This page lists each type, its keys, the evidence collected, and how a contribution is credited to a team. For how the evidence is fetched, see [harvesters.md](harvesters.md).

## Common fields

These apply to every type:

- **`target_geometry`**: a Point, a Polygon, or `null`. `null` means the whole event perimeter (`bounding_polygon`).
- **`window_start` / `window_end`** (optional): a contribution only counts if it was made inside this window as well as inside the event window.
- **`validation_rules.target_count`** (default 1): how many contributions a team needs. Progress is the sum of `element_count` over the team's **verified** submissions for the quest. Points are awarded once, when progress reaches the target.
- **`inspired_by`**: the conference session the quest is based on. It has no effect on verification.

### Usernames

Teams are credited through the platform usernames members give when joining (`POST /api/teams/join/`):

| Platform | Member field used |
|---|---|
| OpenStreetMap, OSM Notes, OpenHistoricalMap | `osm_username` |
| Wikimedia Commons, Wikidata | `wikimedia_username` |
| GitHub | `github_username` |

If the platform username doesn't match a member, the harvester falls back to `user_identifier` and then `display_name`. All comparisons ignore case.

## Summary

| Type | Evidence | Platform | Credited by | Status |
|---|---|---|---|---|
| `osm_tags` | OSM changeset with the hashtag that left elements carrying the required tags | `osm` | `osm_username` | Harvested |
| `osm_notes` | OSM Note closed during the event with the hashtag in a comment | `osm_notes` | `osm_username` | Harvested |
| `ohm_feature` | OpenHistoricalMap changeset with the hashtag that left dated features | `ohm` | `osm_username` | Harvested |
| `wikimedia_commons` | Commons upload whose description has the hashtag | `commons` | `wikimedia_username` | Harvested |
| `wikidata_entry` | Any Wikidata edit with the hashtag in its summary | `wikidata` | `wikimedia_username` | Harvested |
| `wikidata_statement` | Edit to one named item, with the hashtag, touching given properties | `wikidata` | `wikimedia_username` | Harvested |
| `oss_contribution` | GitHub pull request or issue with the hashtag | `github` | `github_username` | Harvested |
| `location_checkin` | Participant's location pings near the target | `checkin` | the pinging member | Owned by the GPS check-in feature |
| `street_imagery` | Panoramax street-level photos in the area | `panoramax` | n/a | Not implemented (stretch) |

---

## `osm_tags`: OpenStreetMap tag rule

Credits a team when one of its mappers' changesets left OSM elements in the target area with all the required tags.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `required_tags` | object | `{}` | `{key: value}`. `"*"` means any value; `"a\|b"` means either value. |
| `target_count` | int | 1 | Distinct matching elements needed, summed across the team's changesets. |
| `radius_m` | number | 300 | Search radius around the target. Only used when `target_geometry` is a Point. |
| `require_hashtag` | bool | `true` | Require the event hashtag on the changeset (`hashtags` tag or `#tag` in the comment). |

**Evidence.** One submission per (changeset, quest). `element_count` is the number of distinct matching elements in that changeset. `diff_payload` holds the changeset (`id`, `user`, `created_at`, `comment`, `hashtags`) and the matched elements (`type`, `id`, `version`, `user`, `timestamp`, `lat`, `lon`, `tags`).

**Credit.** The changeset's `user` is matched against `osm_username`.

```json
{
  "title": "Farm-to-fork hours",
  "description": "Add opening_hours to 5 restaurants or cafes within 400 m of the venue.",
  "criteria_type": "osm_tags",
  "target_geometry": {"type": "Point", "coordinates": [-121.4905, 38.5800]},
  "validation_rules": {
    "required_tags": {"amenity": "restaurant|cafe", "opening_hours": "*"},
    "radius_m": 400,
    "target_count": 5
  },
  "points_reward": 40
}
```

---

## `osm_notes`: OpenStreetMap Note resolved

Credits a team for closing an OSM Note during the event, when the hashtag appears in one of the note's comments.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `target_count` | int | 1 | Notes needed. |
| `radius_m` | number | 300 | When `target_geometry` is a Point: how close the note must be. |

**Evidence.** One submission per (note, quest), with `element_count` 1 and `diff_payload` `{status, comments: [{date, user, action, text}]}`. The note must be inside the quest's area: within `radius_m` of a Point target, inside a Polygon target, or inside the event perimeter.

**Credit.** The user who closed the note, matched against `osm_username`. If the note was closed anonymously, the user who wrote the hashtag comment is used.

```json
{
  "title": "Close a Note",
  "description": "Resolve an open OSM Note in the perimeter. Put #FOSS4GNA2026 in your closing comment.",
  "criteria_type": "osm_notes",
  "target_geometry": null,
  "validation_rules": {"target_count": 1},
  "points_reward": 20
}
```

---

## `ohm_feature`: OpenHistoricalMap feature

Works like `osm_tags`, but on OpenHistoricalMap.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `required_tags` | object | `{"start_date": "*"}` | As for `osm_tags`. |
| `target_count` | int | 1 | Distinct matching features needed. |
| `radius_m` | number | 300 | Point targets only. |
| `require_hashtag` | bool | `true` | As for `osm_tags`. |

**Evidence.** The same as `osm_tags`, with links to `openhistoricalmap.org/changeset/{id}`.

**Credit.** `osm_username`. Most people use the same name on OHM as on OSM.

```json
{
  "title": "Alkali Flat, then and now",
  "description": "Add one Alkali Flat building to OpenHistoricalMap with a start_date.",
  "criteria_type": "ohm_feature",
  "target_geometry": {"type": "Polygon", "coordinates": [[[-121.495, 38.582], [-121.485, 38.582], [-121.485, 38.590], [-121.495, 38.590], [-121.495, 38.582]]]},
  "validation_rules": {"required_tags": {"building": "*", "start_date": "*"}, "target_count": 1},
  "points_reward": 35
}
```

---

## `wikimedia_commons`: Commons photo

Credits a team for a file uploaded to Wikimedia Commons during the event whose description contains the hashtag.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `category` | string | none | If set, the file must be in this category. The `Category:` prefix, letter case, and `_` versus space are all ignored. |
| `target_count` | int | 1 | Files needed. |

**Evidence.** One submission per (file, quest). `diff_payload` holds `pageid`, `title`, `file_url`, `categories`, and the search `snippet`. The upload time (`imageinfo.timestamp`) must be inside the window.

**Credit.** The uploader (`imageinfo.user`), matched against `wikimedia_username`.

Note: `target_geometry` is not checked against the file's location. If an event has several Commons quests, give each one a `category` so a single photo doesn't satisfy all of them.

```json
{
  "title": "Give the venue a face",
  "description": "Upload a photo of the Public Market facade on J St, categorised under Sacramento. Put #FOSS4GNA2026 in the description.",
  "criteria_type": "wikimedia_commons",
  "target_geometry": {"type": "Point", "coordinates": [-121.4930, 38.5797]},
  "validation_rules": {"category": "Sacramento, California", "target_count": 1},
  "points_reward": 20
}
```

---

## `wikidata_entry`: any Wikidata edit

Credits a team for any Wikidata edit whose edit summary contains the hashtag.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `target_count` | int | 1 | Revisions needed. |

**Evidence.** One submission per revision. The `external_id` is the revision id, the link is `https://www.wikidata.org/w/index.php?diff={revid}`, and `diff_payload` is `{entity_id, revid, comment}`. Candidate edits come from a hashtag search and from the contributions of members who shared a `wikimedia_username`. Edit summaries are not searchable, so members **must** share their username for this quest to work reliably. If several `wikidata_entry` quests are open, a revision is credited to the first of them only.

**Credit.** The revision `user`, matched against `wikimedia_username`.

```json
{
  "title": "Any Wikidata improvement",
  "description": "Improve a Wikidata item about downtown Sacramento. Add #FOSS4GNA2026 to the edit summary.",
  "criteria_type": "wikidata_entry",
  "validation_rules": {"target_count": 1},
  "points_reward": 15
}
```

---

## `wikidata_statement`: statement on a named item

Credits a team for an edit to one specific Wikidata item that has the hashtag in its summary and touches one of the listed properties.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `qid` | string | required | The item, e.g. `Q111393295`. Quests without a `qid` are skipped with a warning. |
| `properties` | list of strings | `[]` | Property ids, e.g. `["P84", "P571"]`. The summary must mention at least one of them as a whole token. Wikidata's automatic summaries contain `[[Property:P84]]`. An empty list accepts any hashtag edit to the item. |
| `target_count` | int | 1 | Qualifying revisions needed. |

**Evidence.** One submission per (revision, quest), with `diff_payload` `{qid, revid, properties_touched, comment}`.

**Credit.** The revision `user`, matched against `wikimedia_username`.

Creating a *new* item (plan quest 15) has no QID in advance, so it is not covered by this type yet. Use `wikidata_entry` for it.

```json
{
  "title": "Fill in the architect on Wikidata",
  "description": "Add architect (P84) = Julia Morgan and inception (P571) = 1923 to Q111393295, with #FOSS4GNA2026 in the summary.",
  "criteria_type": "wikidata_statement",
  "validation_rules": {"qid": "Q111393295", "properties": ["P84", "P571"], "target_count": 2},
  "points_reward": 25
}
```

---

## `oss_contribution`: open-source pull request or issue

Credits a team for a GitHub pull request or issue opened during the event with the hashtag in its title or body.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `kinds` | list | `["pr", "issue"]` | Which kinds count. |
| `allowed_owners` | list of strings | none | If set, the repository owner (user or org) must be one of these. Case is ignored. |
| `target_count` | int | 1 | Pull requests or issues needed. |

**Evidence.** One submission per (item, quest), with `diff_payload` `{kind, repo, number, title, state}` and a link to the item on github.com.

**Credit.** `user.login`, matched against `github_username`.

Set `GITHUB_TOKEN` in the deployment environment: without it GitHub allows only 10 search requests a minute.

```json
{
  "title": "Ship a patch",
  "description": "Open a PR or a substantive issue on any OSGeo project, with #FOSS4GNA2026 in the body.",
  "criteria_type": "oss_contribution",
  "validation_rules": {"kinds": ["pr", "issue"], "allowed_owners": ["OSGeo", "qgis", "grass"], "target_count": 1},
  "points_reward": 50
}
```

---

## `location_checkin`: GPS check-in

A participant's foreground location pings land within a set distance of the quest target, optionally for a minimum time. This is checked on the server from `LocationPing` as pings arrive; there is no external API and no harvester. Check-ins are verified automatically.

**Target:** `target_geometry` is required; quests without one are ignored.
- **Point:** used as the target directly.
- **Polygon:** its centroid is the target, and any ping inside the polygon also counts as in range.

**validation_rules**

| Key | Default | Meaning |
|---|---|---|
| `radius_m` | 50 | In range if the ping is within this many metres of the target (haversine distance) |
| `min_minutes` | 0 | Required time in range, from first to latest in-range ping. 0 verifies on the first in-range ping. If no in-range ping arrives for 10 minutes before verification, the clock restarts |
| `target_count` | 1 | Number of distinct participants on a team who must check in before the team completes the quest |

**Evidence:** one Submission per (quest, participant):
- `platform="checkin"`, `external_id="q{quest_id}/{user_identifier}"`
- `author_username` = the participant's display name
- `external_url` = OSM map link to the first in-range position
- `contributed_at` = first in-range time
- `diff_payload` = `{user_identifier, first_seen, dwell_start, last_seen, ping_count, distance_m, radius_m, min_minutes, auto_verified_at?}`

Only pings sent while the quest is open count: the quest must be active and inside its `window_start`/`window_end`. Background pings are ignored.

**Credit:** when the dwell time is met, the submission is verified by `system:checkin` and QuestProgress awards `points_reward` once the team reaches `target_count`. Auto-verification happens at most once, so a host who un-verifies a check-in will not be overridden by later pings. A participant without a team leaves evidence but earns no points; their team is credited on their next in-range ping after they join.

**Participant API**
- `POST /api/locations/ping/` returns `checkins: [{quest, quest_title, status: in_range|verified, distance_m}]`
- `GET /api/locations/checkins/?event=&user_identifier=` returns `[{quest, quest_title, status: verified|pending|revoked, first_seen, last_seen, ping_count, distance_m, radius_m, min_minutes, verified_at}]`

**Example**
```json
{
  "title": "Icebreaker check-in",
  "criteria_type": "location_checkin",
  "target_geometry": {"type": "Point", "coordinates": [-121.48993, 38.57902]},
  "validation_rules": {"radius_m": 60, "min_minutes": 5},
  "window_start": "2026-11-02T18:00:00-08:00",
  "window_end": "2026-11-02T20:00:00-08:00",
  "points_reward": 10
}
```

---

## `street_imagery`: street-level imagery

*Stretch goal, not implemented.* The plan is to search the Panoramax API for sequences in the quest area during the window and match the author by username. The `panoramax` platform and the `PANORAMAX_API` setting already exist, but no harvester calls them yet.
