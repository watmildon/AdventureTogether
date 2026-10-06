# AdventureTogether - Feature Inventory

This document serves as the single source of truth for all implemented and planned features in AdventureTogether. Every architectural enhancement or feature addition must maintain backward compatibility with previously listed features and update this ledger accordingly.

## Feature Registry

| ID | Feature Name | Module | Status | Description & Acceptance Criteria |
|---|---|---|---|---|
| **FEAT-001** | Monorepo Architecture & Scaffolding | Core / Deploy | Completed | Modular folder structure (`frontend/`, `backend/`, `deploy/`, `documentation/`) with zero Redis overhead, PostgreSQL/PostGIS spatial persistence, and unified containerization. |
| **FEAT-002** | Event Lifecycle & Bounding Perimeter | `apps.events` | Completed | Host configuration of scavenger hunt events with title, start/end windows, custom hashtags, and GeoJSON bounding perimeter polygon enforcement. |
| **FEAT-003** | Team Management & Join Codes | `apps.teams` | Completed | Participant team creation and join-code mechanism enabling cooperative groups during quests. |
| **FEAT-004** | Geospatial Quest Builder & Validation Rules | `apps.quests` | Completed | Interactive host interface to draw quest target zones (points, polygons) and set OSM tag criteria, Wikimedia photo categories, and Wikidata targets. |
| **FEAT-005** | Foreground Geolocation & Privacy Matrix | `apps.locations` | Completed | Foreground-only GPS tracking utilizing HTML5 Geolocation and Page Visibility API with privacy tiers (`nobody`, `team`, `quest`) and 20-minute decay retention. |
| **FEAT-006** | Mobile Mapping Deep Linking | Frontend Composables | Completed | One-tap deep link generation for `streetcomplete://` and `everydoor://` pre-centered on active GPS coordinates. |
| **FEAT-007** | Multi-Platform Submission Harvester | `apps.submissions` | Completed | Automated background worker polling OpenStreetMap Changeset API, Wikimedia Commons API, and Wikidata API matching event hashtags. |
| **FEAT-008** | Host Verification Dashboard & Diffs | `apps.submissions` | Completed | Host portal displaying ingested submissions, tag/JSON diff visualizers, external proof links, and verification approval toggles. |
| **FEAT-009** | Ansible Deployment & VM Security Hardening | `deploy/ansible` | Completed | Production Ansible playbooks configuring UFW firewalls, SSH hardening, non-root execution, PostGIS backups, and Dockerized orchestration. |
| **FEAT-010** | Comprehensive Documentation & Guides | `documentation/` | Completed | End-user manuals and developer API documentation detailing architecture, endpoints, and deployment procedures. |
| **FEAT-011** | Simulated GPS Position (testing aid) | Frontend Composables | Completed | Dev-only override of the browser Geolocation API via `?lat=&lng=` query params, persisted in `localStorage`, with a header badge and clear control on the event map. Ignored in production builds unless `VITE_ALLOW_SIMULATED_GPS=true`. See `documentation/local_setup.md`. |
