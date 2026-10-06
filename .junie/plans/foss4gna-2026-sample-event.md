# Plan: FOSS4G NA 2026 Sample Event

Status: **draft for review**. Nothing below is implemented yet.

Goal: ship AdventureTogether's first real event at FOSS4G North America 2026 in Sacramento, with a seeded event, a walkable quest set tied to the conference programme, and a handful of new quest types that fit the Open Data / Open Software theme.

---

## 1. What we know about the conference

Sources: foss4gna.org (home, venue, events, plenary pages), the pretalx schedule export at talks.osgeo.org/foss4g-na-2026 (version 0.6, 127 sessions), OpenStreetMap via Overpass, Wikidata.

| Fact | Value |
|---|---|
| Dates | Mon 2 Nov (workshops) to Wed 4 Nov 2026 |
| Venue | Sheraton Grand Sacramento, 1230 J St, Sacramento CA 95814 |
| Venue in OSM | way 437894396, centroid 38.57902, -121.48993. Tagged `tourism=hotel` + `building=yes` only. No `wikidata`, no `image`, no `historic`, no architect. |
| Venue in Wikidata | Q111393295 exists but the historic story (1923 Sacramento Public Market, architect Julia Morgan) is not reflected in OSM, and there is no Wikidata item for the Public Market at all |
| Session rooms | Tofanelli, Bataglieri, Compagno, Bondi, Beavis, Carr, Gardenia |
| Tracks | Technical, Application, Community of Practice, Business of Open Source |
| Theme | "Resilience and Innovation": open data, water, wildfire, environmental resilience |
| Social programme | Mon 18:00 Welcome Icebreaker BBQ; Tue 18:00 Night Out (self-organised farm-to-fork dinners) and Night In (puzzles, board games, drop-in workshops on OpenHistoricalMap by Minh Nguyễn and Hand Drawn Maps by Michele Tobias); Wed 10:30 Birds of a Feather; Wed 13:00 NASA Open Science Essentials |
| City | Flat grid, very walkable. Old Sacramento Waterfront, State Capitol, Crocker Art Museum, American River Parkway all within reach |

The conference "Map" page is a Squarespace page with no embedded map data, so there is no official venue map to import. The detailed schedule is in Whova and pretalx; pretalx is the machine-readable source and has a stable JSON export.

## 2. Key locations (from OSM, all within ~800 m of the venue)

Walking distances from the Sheraton front door. Flags show what is missing in OSM today, which is what makes each a quest candidate.

| Location | OSM id | Dist | Missing in OSM |
|---|---|---|---|
| Sheraton Grand (venue) | w437894396 | 0 | wikidata, image, historic/architect tags |
| Cathedral of the Blessed Sacrament statues (Saint Patrick, Our Lady of Mount Carmel, Saint Joseph, Saint Anthony) | n7715064749 etc. | 90 m | wikidata; images exist |
| Cesar E. Chavez Plaza | w37060141 | 260 m | image |
| A.J. Stevens statue (in the plaza) | n12368605121 | 250 m | wikidata, image |
| Sacramento City Hall | w120719515 | 330 m | image |
| Sacramento Historic City Hall | w331127166 | 300 m | wikidata, image |
| Ruhstaller Building | w331119613 | 290 m | nothing, fully tagged; good "check-in" reference point |
| Sacramento Central Public Library | w331127165 | 390 m | image |
| California State Capitol + Capitol Park memorials (Thomas Starr King, USS California, Spanish War Veterans, Firefighters, Peace Officers, Vietnam Veterans) | r20084, n5370737515 … | 380–550 m | most memorials lack wikidata and image |
| Sacramento Memorial Auditorium | w120726088 | 520 m | wikidata (Q125912237 exists), image |
| Governor's Mansion State Historic Park | w40180170 | 580 m | image |
| Leland Stanford Mansion | n368173324 | 660 m | image |
| The California Museum | n368174474 | 700 m | image |
| Alkali Flat historic districts (3) | n358836500 … | 550–780 m | wikidata on two of three |
| Old Sacramento: Pony Express Monument, Theodore Judah Monument | n358836111, n358836117 | ~1.2 km | mixed |
| Farm-to-fork cluster around 12th/J to 10th/K: ~17 restaurants, 6 cafes, 1 pub | n12853920681 … | 40–340 m | 13 of 17 restaurants and 4 of 6 cafes have no `opening_hours` |
| Bicycle parking | 685 nodes in the wider box, 400 within 800 m | everywhere | effectively none have `capacity`, `bicycle_parking` type, or `covered` |
| Drinking water | 11 nodes, 8 unnamed | scattered | no `bottle`, `wheelchair`, or `fee` tags |

## 3. Proposed event record

| Field | Proposed value |
|---|---|
| title | FOSS4G NA 2026 Open Data Hunt |
| slug | foss4gna-2026 |
| hashtag | `FOSS4GNA2026` (see open question 1) |
| start_time | 2026-11-02 08:00 America/Los_Angeles |
| end_time | 2026-11-04 18:00 America/Los_Angeles |
| bounding_polygon | Rectangle lon -121.509 to -121.481, lat 38.572 to 38.590. Covers the venue, Capitol and park, Crocker Art Museum, Old Sacramento Waterfront, Alkali Flat, and the Memorial Auditorium / Governor's Mansion block to the east. About 2.4 km by 2 km. |
| description | Walk downtown Sacramento between sessions, fix the map, and feed photos and facts back into OSM, Wikimedia Commons, Wikidata and OpenHistoricalMap. Every quest is inspired by a talk on the programme. |

## 4. Quest types

### 4.1 Existing types, used as-is

- `osm_tags`: an OSM changeset in the perimeter with the hashtag touched an element matching required tags.
- `wikimedia_commons`: a file uploaded with the hashtag.
- `wikidata_entry`: any Wikidata edit found by hashtag search (currently shallow; see 4.3).

### 4.2 New quest types to build

| Type key | What it verifies | How it is harvested | Inspired by |
|---|---|---|---|
| `location_checkin` | A participant's foreground location pings landed within N metres of the target for at least M minutes | Server-side only, from `LocationPing`. No external API. Auto-verifies. | Lets us make "go and look" quests for memorials, plaques, and the Night Out restaurants |
| `osm_notes` | A participant resolved (closed) an OSM Note inside the perimeter, or opened one with the hashtag | OSM Notes API: `/api/0.6/notes?bbox=…&closed=…` filtered by `closed_at` in the window and hashtag in the closing comment | "The OpenStreetMap platform today" (Minh Nguyễn, Wed 13:30) |
| `ohm_feature` | A changeset on OpenHistoricalMap in the perimeter with the hashtag that adds a feature with `start_date` (and ideally `end_date`) | Same code path as the OSM harvester with the base URL switched to `https://www.openhistoricalmap.org/api/0.6` | "OpenHistoricalMap: across the geoverse" (Wed 11:00) and the Tuesday Night In OHM drop-in |
| `wikidata_statement` | A specific property was added to a specific item (e.g. P84 architect = Julia Morgan on Q111393295) with the hashtag in the edit summary | Wikidata `action=query&prop=revisions` on the named QID, scan summaries for the hashtag and the property id. Replaces the current text-search approach for targeted quests. | "We Scanned These Maps. Now What?" (Michele Tobias, Wed 14:00); the venue's own history |
| `oss_contribution` | A pull request or issue opened on an OSGeo-family repository with the hashtag in the body | GitHub search API (`is:pr "#FOSS4GNA2026"`), optionally GitLab. Author matched to team by GitHub username. | "Code is liability – contributing to GDAL in the LLM era" (Howard Butler, Tue 11:00), "State of GRASS", "OSGeo updates" |
| `street_imagery` (stretch) | Street-level photos uploaded to Panoramax within the perimeter during the window | Panoramax API search by bbox and date, author matched by username | "Point Clouds from Your Pocket" (Tue 13:50), "Rebuilding OpenAerialMap" (Wed 13:00) |

Two enhancements to existing behaviour that the quest set depends on:

- **`target_count`** in `validation_rules` is documented but never enforced. Make `osm_tags` count distinct matching elements across a team's changesets and only complete when the count is reached. Needed for "add hours to 5 cafes" style quests.
- **Talk linkage.** Add `inspired_by` to `Quest`: a JSON blob `{title, speakers, when, room, url}` populated from pretalx. The map popup and quest list show "Inspired by: … (Tue 16:00, Beavis)" with a link.

### 4.3 Harvester fixes required for any of this to work in production

- OSM changeset query is bbox-only today; add `time=` (event window) and `limit`/pagination, and match the `hashtags=` changeset tag exactly rather than substring on the comment.
- Commons and Wikidata harvesters hard-code the author as "Wikimedia Uploader" / "Wikidata Contributor", so team attribution never works. Pull the real uploader (`imageinfo.user`) and revision user.
- Nothing schedules the harvester. Register a Django-Q2 schedule (every 5 minutes during the event window) and the ping cleanup.
- Participants need a way to tell us their OSM / Wikimedia / GitHub usernames. Add optional `osm_username`, `wikimedia_username`, `github_username` to `TeamMembership` and use them in `match_author_to_team` instead of guessing from display names.

## 5. Proposed quests

Points are rough: 10 for a check-in, 15–25 for a single edit, 30–50 for a counted or multi-step quest. Each row names the inspiring session; `inspired_by` on the quest will carry the pretalx link.

### Monday: warm-up around the venue

| # | Quest | Type | Target / rules | Pts | Inspired by |
|---|---|---|---|---|---|
| 1 | **Julia Morgan built this.** Add `architect=Julia Morgan`, `start_date=1923`, `historic=building`, `wikidata=Q111393295` to the Sheraton building in OSM | osm_tags | w437894396; required `architect=*`, `wikidata=*` | 25 | Venue history; "We Scanned These Maps" |
| 2 | **Give the venue a face.** Upload a photo of the restored Public Market façade on J St to Commons, categorised under Sacramento | wikimedia_commons | target point at the J St entrance | 20 | Plenary venue |
| 3 | **Fill in the architect on Wikidata.** Add P84 (architect) = Q274663 (Julia Morgan) and P571 (inception) = 1923 to Q111393295 | wikidata_statement | QID Q111393295, properties P84, P571 | 25 | "We Scanned These Maps" (Tobias) |
| 4 | **Farm-to-fork hours.** Add `opening_hours` to 5 restaurants or cafes within 400 m of the venue (13 of 17 lack it) | osm_tags | `amenity=restaurant|cafe`, `opening_hours=*`, `target_count=5` | 40 | Night Out logistics; StreetComplete |
| 5 | **Icebreaker check-in.** Be at the Welcome Icebreaker | location_checkin | venue, radius 60 m, Mon 18:00–20:00 | 10 | Conference Events |

### Tuesday: resilience, accessibility, community

| # | Quest | Type | Target / rules | Pts | Inspired by |
|---|---|---|---|---|---|
| 6 | **Shade the grid.** Map 10 street trees on the blocks between the venue and Cesar Chavez Plaza with `natural=tree` and `leaf_type` | osm_tags | `natural=tree`, `leaf_type=*`, `target_count=10` | 40 | "Empowering people to map the urban heat island effect" (Joseph, Tue 16:00); "Detecting, mapping… trees using RGB drone imagery" (Young) |
| 7 | **Every kerb counts.** Tag 5 pedestrian crossings around Capitol Park with `tactile_paving` and `kerb` | osm_tags | `highway=crossing`, `tactile_paving=*`, `kerb=*`, `target_count=5` | 40 | "Cities, unmapped: Pedestrian Infrastructure with Tile2Net" (Hosseini, Tue 15:30); "Open-Source R Workflows… Accessibility Analysis" (Tilles) |
| 8 | **Lock it up.** Add `capacity` and `bicycle_parking` type to 10 of the 400 untagged bike racks within 800 m | osm_tags | `amenity=bicycle_parking`, `capacity=*`, `target_count=10` | 30 | "Routes to Safety" (Kumar) and the city's bikeable-grid pitch |
| 9 | **Water, mapped.** Survey the 8 unnamed `drinking_water` nodes: add `bottle=*` and `wheelchair=*` or confirm they still exist | osm_tags | `amenity=drinking_water`, `bottle=*`, `target_count=3` | 25 | Conference theme: water and resilience |
| 10 | **Close a Note.** Resolve an open OSM Note anywhere in the perimeter | osm_notes | perimeter, closed in window, hashtag in comment | 20 | "The OpenStreetMap platform today" (Nguyễn) |
| 11 | **Memorial roll call.** Photograph the four Capitol Park memorials that lack images (USS California, Spanish War Veterans, Firefighters, Peace Officers) and link them from OSM with `image=` or `wikimedia_commons=` | wikimedia_commons + osm_tags (two quests, or one multi-step) | points at each memorial | 30 | "The Archiving and Preservation of Public Geospatial Data" (Durante, Majewicz) |
| 12 | **Capitol check-in.** Stand at the west steps of the State Capitol | location_checkin | r20084 west entrance, radius 50 m | 10 | "Geospatial AI Agents in Practice: Sacramento Open Data" (O'Beirne, Toms, Tue 14:00) |
| 13 | **Night Out hours.** After dinner, add or correct `opening_hours` for the restaurant your group ate at | osm_tags | `amenity=restaurant`, `opening_hours=*` | 15 | Night Out |

### Wednesday: history, transit, code

| # | Quest | Type | Target / rules | Pts | Inspired by |
|---|---|---|---|---|---|
| 14 | **Alkali Flat, then and now.** Add one building in Alkali Flat to OpenHistoricalMap with `start_date` | ohm_feature | polygon over the three Alkali Flat districts | 35 | "OpenHistoricalMap: across the geoverse" (Nguyễn, Wed 11:00); Tue Night In drop-in |
| 15 | **Public Market, 1923–1974.** Create the Wikidata item for the Sacramento Public Market (none exists) with P31, P625, P84, P571, P576 and link it as P1366/P138 from Q111393295 | wikidata_statement | new item; verified by hashtag on creation summary | 50 | Venue history |
| 16 | **Stop and tag.** Add `shelter`, `bench`, and `gtfs:stop_id` (from Cal-ITP's open GTFS) to 3 SacRT stops on the 12th St / K St light rail and bus corridor | osm_tags | `public_transport=platform`, `gtfs:stop_id=*`, `target_count=3` | 35 | "Open Transit Data from Cal-ITP" (Siroky, Ritezel, Wed 15:30) |
| 17 | **Ship a patch.** Open a PR or substantive issue on any OSGeo project repository with the hashtag in the body | oss_contribution | GitHub search | 50 | "Code is liability" (Butler), "State of GRASS" (White), "OSGeo updates" (Kralidis, Ticheler) |
| 18 | **Old Sac check-in.** Walk to the Pony Express Monument and photograph the Theodore Judah Monument for Commons | location_checkin + wikimedia_commons | n358836111 radius 40 m; n358836117 | 25 | "Cliopatria" / history track; Visit Sacramento |
| 19 | **Street view, open.** (stretch) Capture a Panoramax sequence along K St between 10th and 13th | street_imagery | bbox over K St | 30 | "Point Clouds from Your Pocket" (McAndrew); "Rebuilding OpenAerialMap" (Giovando) |
| 20 | **Closing plenary check-in.** Be in the building for the closing plenary | location_checkin | venue, radius 60 m, Wed 16:00–17:00 | 10 | Schedule |

Twenty quests is a lot for a three-day conference with a full programme; I would aim to ship 12 to 14 and keep the rest as a backlog. My cut list if we need to trim: 19 (stretch), 16 (needs GTFS cross-reference), 9, 13.

## 6. Work breakdown

Ordered so each step leaves the app working.

1. **Data model.** Add `inspired_by` JSON to `Quest`; add `osm_username`, `wikimedia_username`, `github_username` to `TeamMembership`; add the new `criteria_type` choices. Migrations, serializers, tests.
2. **Seed command.** `manage.py seed_event path/to/event.json` that upserts an event, its quests, and `inspired_by` data from a JSON file. Commit `backend/fixtures/foss4gna_2026.json` built from the tables above. Also a `--from-pretalx URL` helper that fills `inspired_by` from the schedule export by talk code.
3. **Harvester hardening.** Time window and hashtag-tag matching for OSM; real author extraction for Commons and Wikidata; Django-Q2 schedule; ping cleanup schedule. Unit tests against recorded API fixtures.
4. **`target_count` enforcement** in the matcher and a `progress` field on the quest-per-team relationship (new `QuestProgress` model: team, quest, count, completed_at). Verification awards points when complete.
5. **`location_checkin`** type: matcher runs on each ping, writes `QuestProgress`, auto-verifies. Host can still revoke.
6. **`osm_notes`** and **`ohm_feature`** harvesters (small, reuse OSM code).
7. **`wikidata_statement`** harvester (targeted revision scan).
8. **`oss_contribution`** harvester (GitHub search; needs a token in env for rate limits).
9. **Frontend.** Quest builder gains the new types and an "inspired by" picker that searches the pretalx export; map popups and a quest list panel show inspiration, progress (3 of 5), and completion; team scoreboard on the event page.
10. **Docs.** `documentation/` pages for the seed file format and each quest type; FEATURES.md rows.
11. **Stretch.** `street_imagery` via Panoramax.

Not in this plan but blocking a public deployment: authentication for host routes, and the phone-width map layout. Both are tracked separately.

## 7. Open questions for review

1. **Hashtag.** `#FOSS4GNA2026` is probably what the conference will use on social media, which means unrelated OSM edits elsewhere could carry it too. The bbox filter handles OSM, but Commons and Wikidata searches are global. Alternative: a hunt-specific tag like `#FOSS4GNA2026hunt`, less discoverable but unambiguous. Which do you prefer?
2. **Perimeter.** Include Old Sacramento (1.2 km walk) and the Crocker, or keep it tight around the Capitol / venue core so quests are doable between sessions?
3. **Check-in quests.** Are proof-of-presence quests in the spirit of the app, or should every quest produce open data? They are cheap to build and good for onboarding, but they are not contributions.
4. **GitHub quest.** Fine to require a GitHub API token in the deployment env? Without it the search endpoint allows only 10 requests a minute unauthenticated.
5. **Day gating.** Should quests have their own time windows (e.g. the icebreaker check-in only on Monday evening), or is the event window enough? That is a small model addition.
6. **Points and prizes.** Is there a prize, and does the scoreboard need to be public on the event page before the closing plenary?
7. **Wikidata creation quest (#15).** Creating an item is a bigger ask than adding a statement, and verification of a new item by hashtag is fiddly. Keep, or reduce to adding statements on the existing hotel item?
8. **Pretalx as the schedule source.** The site says "Powered by Whova", but pretalx has the JSON export. Any reason to prefer Whova?
