# AdventureTogether - Infrastructure & Deployment Guide

This guide provides step-by-step instructions for running AdventureTogether in local development, containerized production environments, and provisioning production virtual machines using Ansible.

---

## 1. System Architecture

```
[ Nginx Web Server (Port 80) ]
        │
        ├──> [ / : Single Vue 3 SPA (Vite, Pinia, Scoped CSS) ]
        │
        └──> [ /api/* : Django REST API + GeoDjango (Port 8000) ]
                    │
                    ├──> [ PostgreSQL 16 + PostGIS 3.4 (Port 5432) ]
                    │           ▲
                    │           │ (ORM Broker)
                    └──> [ Django-Q2 Harvester Worker ]
```

**Key Architectural Features**:
- **Zero-Redis Stack**: Task queuing (Django-Q2) and location temporal decay run directly on PostgreSQL/PostGIS, minimizing RAM footprint.
- **Code-Split Vue SPA**: Host management modules are lazy-loaded on demand to ensure minimal initial payload for field participants on mobile devices.

---

## 2. Local Development Setup

### Prerequisites
- Python 3.12+ with GDAL & SpatiaLite installed
- Node.js 18+ and npm

### 2.1 Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### 2.2 Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The Vite development server runs at `http://localhost:3000` with automated proxying to the Django backend.

---

## 3. Production Docker Deployment

Deploy the full containerized stack using Docker Compose:
```bash
docker compose up -d --build
```

### Secrets and External API Configuration
The backend and worker containers read these from the environment (Docker Compose passes them through from your shell or from `deploy/.env`):

| Variable | Required | Purpose |
|---|---|---|
| `OVERPASS_URL` | Yes, for Overpass-based checks | Overpass API interpreter endpoint, e.g. `https://overpass-api.de/api/interpreter` |
| `GITHUB_TOKEN` | Optional | Raises GitHub search rate limits for `oss_contribution` quests |
| `OSM_API_BASE`, `OHM_API_BASE`, `WIKIMEDIA_COMMONS_API`, `WIKIDATA_API`, `PANORAMAX_API`, `HARVEST_USER_AGENT` | No | Override the public API defaults in `settings.py` |

Set `OVERPASS_URL` in the environment; locally `export OVERPASS_URL="$(cat ~/.overpassurl)"`; never commit it. The same applies to `GITHUB_TOKEN`: keep both out of compose files, scripts, logs, and commit messages. `deploy/.env` is gitignored.

### Container Registry:
1. `adventure_together_db`: PostGIS 16-3.4 spatial database with persistent volume `postgis_data`.
2. `adventure_together_backend`: Django REST API with GeoDjango.
3. `adventure_together_worker`: Background Harvester worker running `python manage.py qcluster`.
4. `adventure_together_frontend`: Vue 3 SPA served via optimized Nginx with Gzip compression.

---

## 4. Production VM Provisioning with Ansible

The playbooks in `deploy/ansible/` configure an Ubuntu/Debian server from scratch with non-root execution, UFW firewall rules, Fail2ban protection, and daily automated PostGIS backups.

### Running Ansible Playbook
```bash
cd deploy/ansible
ansible-playbook -i inventory.ini playbook.yml
```

### Supplying Secrets to Ansible
The `application` role writes `{{ project_root }}/deploy/.env` (mode `0600`, task output hidden with `no_log`) from the variables `overpass_url` and `github_token`, so Docker Compose picks them up on the server. Provide them one of two ways:

1. **ansible-vault**: copy `group_vars/scavenger_servers.yml.example` to `group_vars/scavenger_servers.yml`, fill it in, run `ansible-vault encrypt group_vars/scavenger_servers.yml`, and add `--ask-vault-pass` to the playbook command.
2. **--extra-vars**: `ansible-playbook -i inventory.ini playbook.yml -e overpass_url="$(cat ~/.overpassurl)" -e github_token="$GITHUB_TOKEN"`.

`deploy/ansible/group_vars/*.yml` is gitignored. Never commit the real file; keep even vault-encrypted copies out of the public repository.

### Automated Backup & Disaster Recovery
- **Daily Cron Backup**: Runs at 02:00 UTC, outputting to `/var/backups/adventuretogether/postgis_backup_<timestamp>.sql.gz`.
- **Retention**: Automatically purges backups older than 14 days.
- **Restore Command**:
```bash
gunzip < /var/backups/adventuretogether/postgis_backup_<timestamp>.sql.gz | docker exec -i adventure_together_db psql -U postgres -d adventure_together
```
