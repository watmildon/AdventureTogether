# Local Development Setup

How to get AdventureTogether running on your machine. Two paths are covered: running natively on macOS (no Docker), and running the full stack with Docker Compose. The native path is what works today on an Apple Silicon Mac with Homebrew.

For production deployment see [deployment_guide.md](deployment_guide.md).

---

## 1. What you are setting up

| Piece | Tech | Port |
|---|---|---|
| Backend API | Django 5 + GeoDjango + Django REST Framework | 8000 |
| Database | PostGIS (Docker) or SpatiaLite (native, zero config) | 5432 / file |
| Background worker | Django-Q2 (`manage.py qcluster`), uses the DB as its broker | n/a |
| Frontend | Vue 3 + Vite + Leaflet | 3000 (dev) / 80 (Docker) |

The Vite dev server proxies `/api/*` to the backend on port 8000, so in development you only open `http://localhost:3000`.

---

## 2. Native setup on macOS (recommended for development)

### 2.1 Prerequisites

GeoDjango needs the GDAL, GEOS, and SpatiaLite C libraries. The macOS system Python (3.9) is too old for Django 5 and its `sqlite3` module cannot load extensions, so install a Homebrew Python too.

```bash
brew install gdal libspatialite python@3.12
```

Node 18+ and npm are required for the frontend. Node 26 is known to work for running the app but breaks part of the Vitest suite (see section 6).

### 2.2 Backend

```bash
cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

GeoDjango cannot locate Homebrew's shared libraries on its own, and `settings.py` defaults the SpatiaLite path to a Linux `.so` name. Export these before running any `manage.py` command:

```bash
export GDAL_LIBRARY_PATH=/opt/homebrew/lib/libgdal.dylib
export GEOS_LIBRARY_PATH=/opt/homebrew/lib/libgeos_c.dylib
export SPATIALITE_LIBRARY_PATH=/opt/homebrew/lib/mod_spatialite.dylib
unset POSTGRES_DB   # when unset, settings.py falls back to SpatiaLite

# External API credentials for the harvesters. Both are secrets: never commit or paste them.
export OVERPASS_URL="$(cat ~/.overpassurl)"   # private Overpass endpoint; if unset, osm_tags quests are skipped (no automatic public fallback)
export GITHUB_TOKEN=...                       # optional; raises GitHub search rate limits for oss_contribution quests
```

Consider putting those lines in a `backend/.env.local` (gitignored) and sourcing it, or in your shell profile.

Then migrate and run:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Check it is alive:

```bash
curl http://127.0.0.1:8000/api/health/
# {"status":"healthy", ..., "database_engine":"django.contrib.gis.db.backends.spatialite", ...}
```

The SpatiaLite database is written to `backend/db.sqlite3`, which is gitignored.

### 2.3 Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The `/api` proxy target can be overridden with `VITE_BACKEND_URL` if the backend is not on `localhost:8000`.

### 2.4 Background worker (optional)

The harvesters (OpenStreetMap via Overpass, OSM Notes, OpenHistoricalMap, Wikimedia Commons, Wikidata, GitHub) run in a Django-Q2 cluster. Register the schedules once (safe to rerun), then start the cluster:

```bash
cd backend
.venv/bin/python manage.py setup_schedules   # harvest every 5 min, ping cleanup every 10 min
.venv/bin/python manage.py qcluster
```

The scheduled harvest only touches events whose window (start - 1 day to end + 1 day) contains the current time. To run one harvest by hand and see the stats, use `manage.py harvest_event <event_id> [--dry-run]`. See [harvesters.md](harvesters.md) for details.

The harvest can also be triggered from the Host Verification page ("Poll External APIs Now") or with:

```bash
curl -X POST http://127.0.0.1:8000/api/submissions/trigger_harvest/ \
  -H 'Content-Type: application/json' -d '{"event": 1}'
```

That call runs synchronously inside the request and does not need the worker.

---

## 3. Docker Compose setup

Requires Docker Desktop. This brings up PostGIS, the API, the worker, and an Nginx container serving the built SPA.

```bash
docker compose up -d --build
```

| Service | URL |
|---|---|
| Frontend (Nginx) | http://localhost |
| API | http://localhost:8000/api/ |
| PostGIS | localhost:5432 (`postgres` / `postgres`) |

Environment defaults live in [docker-compose.yml](../docker-compose.yml). The backend container runs `manage.py runserver` with `DJANGO_DEBUG=True`, so this is a development stack, not a hardened one. Migrations are not run automatically; run them once after the DB is healthy:

```bash
docker compose exec backend python manage.py migrate
```

---

## 4. Seeding demo data

A fresh database is empty and the UI has no screen for creating events, so create one through the API. The `slug` is optional and is generated from the title when omitted.

```bash
# Event with a bounding polygon over downtown San Francisco
curl -sS -X POST http://127.0.0.1:8000/api/events/ -H 'Content-Type: application/json' -d '{
  "title": "Downtown SF Demo Hunt",
  "description": "Demo event for local testing.",
  "hashtag": "AdventureTogetherDemo",
  "bounding_polygon": {"type":"Polygon","coordinates":[[[-122.425,37.770],[-122.395,37.770],[-122.395,37.800],[-122.425,37.800],[-122.425,37.770]]]},
  "start_time": "2026-10-05T00:00:00Z",
  "end_time": "2026-10-12T23:59:59Z"
}'

# A quest inside that polygon (replace "event" with the id returned above)
curl -sS -X POST http://127.0.0.1:8000/api/quests/ -H 'Content-Type: application/json' -d '{
  "event": 1,
  "title": "Cafe opening hours",
  "description": "Add opening_hours to a cafe.",
  "criteria_type": "osm_tags",
  "validation_rules": {"required_tags": {"amenity": "cafe", "opening_hours": "*"}},
  "target_geometry": {"type":"Point","coordinates":[-122.4194,37.7749]},
  "points_reward": 15
}'

# A team (the response includes the join code to enter in the UI)
curl -sS -X POST http://127.0.0.1:8000/api/teams/ -H 'Content-Type: application/json' \
  -d '{"event": 1, "name": "Team Compass"}'
```

Quest geometry must fall inside the event polygon or the API rejects it. Quests can also be added from the Host Builder page once an event exists. The Django admin at `/admin/` is another option after `manage.py createsuperuser`.

Pages to try once seeded:

- `/` lists events
- `/events/1/map` participant map, location sharing, and deep links into StreetComplete / EveryDoor
- `/events/1/join` join or create a team
- `/events/1/host/builder` add quests by clicking the map
- `/events/1/host/verify` review and verify harvested submissions

Browsers only expose geolocation on `localhost` or HTTPS. To test on a phone against the Vite dev server over the LAN you will need an HTTPS tunnel or a self-signed cert.

### Simulating a GPS position

The map page needs a GPS fix before it shows the mapping-tool deep links or sends location pings. For testing on a desktop, or to pretend you are inside an event perimeter, add `lat` and `lng` query parameters to the map URL:

```
http://localhost:3000/events/1/map?lat=37.781&lng=-122.412
```

That position is used instead of the browser's Geolocation API (no permission prompt) and is remembered in `localStorage` under `simulated_gps`, so later visits keep using it until you click **clear** on the "Simulated GPS" badge in the page header. The coordinates above sit inside the demo event seeded in section 4.

Simulation is honoured only in `npm run dev` builds. A production build ignores it unless it was built with `VITE_ALLOW_SIMULATED_GPS=true`, which is intended for staging environments only.

---

## 5. Running the tests

Backend (needs the same env vars as section 2.2):

```bash
cd backend && .venv/bin/python -m pytest
```

Frontend:

```bash
cd frontend && npx vitest run
```

---

## 6. Troubleshooting

**`Could not find the GDAL library` or `GEOS_LIBRARY_PATH` errors.** The env vars from section 2.2 are not set in the shell running `manage.py`. Verify with `ls /opt/homebrew/lib/libgdal.dylib`.

**`Unable to load the SpatiaLite library extension`.** Either `SPATIALITE_LIBRARY_PATH` is unset (it defaults to the Linux `mod_spatialite.so`) or you are using the macOS system Python, whose `sqlite3` module cannot load extensions. Use the Homebrew Python for the venv.

**Backend connects to Postgres unexpectedly.** `settings.py` switches to PostGIS whenever `POSTGRES_DB` is set in the environment. Unset it for SpatiaLite.

**Frontend tests fail with `Cannot read properties of undefined (reading 'clear')` on `localStorage`.** Node 22+ ships a native `localStorage` global that is undefined unless Node is started with `--localstorage-file`, and it shadows the jsdom implementation Vitest provides. `frontend/src/__tests__/setup.ts` works around this; if you see the error, check that `setupFiles` in `vite.config.ts` still points at it.

**Map tiles do not load.** Tiles come from the public OpenStreetMap tile servers and need internet access. The Leaflet CSS is also loaded from a CDN in `frontend/index.html`.

**Port already in use.** Vite is pinned to 3000 and Django to 8000 in the instructions above. Change the Django port freely; if you change Vite's, update nothing else, but if you change Django's, set `VITE_BACKEND_URL`.
