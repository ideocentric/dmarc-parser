# DMARC Intelligence Platform

Multi-tenant DMARC aggregate report ingestion, analysis, and alerting system. Supports file-drop and IMAP-based report collection, a single PostgreSQL database with per-client row-level scoping, pluggable intelligence rules, and a React web UI.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Production Deployment](#production-deployment)
- [Quick Start — Docker (Functional Testing)](#quick-start--docker-functional-testing)
- [Local Development Setup](#local-development-setup)
- [Running the Stack](#running-the-stack)
- [Database Migrations](#database-migrations)
- [CLI Management](#cli-management)
- [Dropping DMARC Reports](#dropping-dmarc-reports)
- [Intelligence Rules](#intelligence-rules)
- [IMAP Ingestion](#imap-ingestion)
- [Adding Clients and Users](#adding-clients-and-users)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [License](#license)
- [Third-Party Attributions](#third-party-attributions)

---

## Architecture Overview

```mermaid
flowchart TD
    Browser(["Browser"])
    Reports(["DMARC Reports\n.xml.gz / .zip"])

    FE["React Frontend\nVite + shadcn/ui\n:5173 dev · :5010 Docker"]

    API["FastAPI Backend\nuvicorn :8000\nJWT · Azure SSO · APScheduler"]

    DB[("PostgreSQL — single database\nclient_id-scoped tables:\nclients · users · domains\nreports · records · flags\nauth_results · processed_files")]

    subgraph ingestion["Ingestion Pipeline"]
        W["File Watcher\nwatchdog\nincoming/{client}/"]
        P["extract → parse → dedup\n→ write → intelligence → archive"]
    end

    Browser --> FE
    FE -->|"/api/*"| API
    API <--> DB
    Reports --> W
    W --> P
    P --> DB
```

Three deployment topologies are supported — see [Production Deployment](#production-deployment) for details.

**Multi-tenancy:** A single database holds all clients. Every DMARC data table (`reports`, `records`, `flags`, `processed_files`) carries a `client_id` column — all queries are automatically scoped to the authenticated user's permitted clients. Super-admins can query across all clients.

**User roles:**

| Global role | Per-client role | Access |
|---|---|---|
| `super_admin` | (not applicable) | Everything — all clients, all users, cross-client analytics |
| `user` | `admin` | Manages assigned clients: domains, IMAP config, and can reset passwords for other users on those clients |
| `user` | `viewer` | Read-only access to assigned client data; can change own password |

A user can hold different per-client roles on different clients (e.g. admin on one, viewer on another).

---

## Production Deployment

Full production deployment uses Terraform to provision infrastructure on **AWS** or **Azure**, GitHub Actions for CI/CD, and `docker-compose.prod.yml` to run the stack. Three topologies are available:

| Topology | Description | When to use |
|---|---|---|
| `standalone` | All services — including PostgreSQL — on one VM | Development, small deployments |
| `split_vm` | App VM in a public subnet; PostgreSQL VM in a private subnet | Separation without managed service cost |
| `split_managed` | App VM in a public subnet; AWS RDS or Azure PostgreSQL Flexible Server | Production, compliance requirements |

**Terraform configurations:**
- `terraform/aws/` — VPC, EC2, ECR, IAM, RDS (all three topologies)
- `terraform/azure/` — VNet, VM, ACR, Managed Identity, PostgreSQL Flexible Server (all three topologies)

**CI/CD:** `.github/workflows/deploy.yml` (AWS) and `.github/workflows/deploy-azure.yml` (Azure) build images on push to `main`, push to the container registry, and deploy via AWS SSM or Azure Run Command without requiring SSH access from CI runner IPs.

See [docs/deployment-guide.md](docs/deployment-guide.md) for the complete step-by-step guide covering Terraform provisioning, CI/CD setup, certbot SSL bootstrap, split-topology database configuration, and backup procedures.

---

## Quick Start — Docker (Functional Testing)

The recommended way to run a complete working environment.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)

### 1. Build and start

```bash
docker compose --env-file .env.docker up --build -d
```

On first boot the stack:
- Starts PostgreSQL
- Runs Alembic migrations to create the schema
- Creates a `super_admin` user
- Creates a `test-client` account with an incoming drop folder

### 2. Open the web UI

```
http://localhost:5010
```

**Default credentials:**

| Field | Value |
|---|---|
| Email | `admin@example.com` |
| Password | `changeme123` |

> Change these in `.env.docker` before exposing this environment to a network.

### 3. Drop a DMARC report

Copy any `.xml.gz` or `.zip` DMARC aggregate report into:

```
docker-data/reports/incoming/test-client/
```

The watcher container picks it up within seconds, processes it, and moves it to:

```
docker-data/reports/archive/test-client/YYYY-MM/
```

Reports, records, and any intelligence flags appear immediately in the UI.

### 4. Enable GeoIP detection (optional)

Without a GeoIP database the system logs an informational message and continues normally — all other intelligence rules still run. To enable geo-anomaly flagging:

1. Create a free [MaxMind account](https://www.maxmind.com/en/geolite2/signup)
2. Download **GeoLite2-City.mmdb** (recommended — provides country, city, region, and coordinates)
   - `GeoLite2-Country.mmdb` also works if you only need country-level data
3. Place the file in the `geoip/` directory at the project root:
   ```
   geoip/GeoLite2-City.mmdb
   ```
   This directory is mounted **separately** from `docker-data/`, so a data reset never deletes the GeoIP database.
4. Restart the containers:
   ```bash
   docker compose --env-file .env.docker restart
   ```

The system auto-detects which database type is loaded. With the City database, each processed record is enriched with country, city, subdivision (state/region), latitude, and longitude.

### 5. Add another test client

```bash
docker compose --env-file .env.docker exec api python -m cli.manage create-client acme "Acme Corp"
```

Then drop files into `docker-data/reports/incoming/acme/`.

### 6. Watch processing logs

```bash
# File watcher activity
docker compose logs -f watcher

# API / migration logs
docker compose logs -f api
```

### 7. Stop the stack

```bash
docker compose down
```

Report files and PostgreSQL data persist in `./docker-data/` between restarts.

**Reset report files only** (keeps database and GeoIP):

```bash
rm -rf docker-data/reports
docker compose --env-file .env.docker up -d
```

**Full reset** (wipes database and reports, keeps GeoIP):

```bash
docker compose down -v && rm -rf docker-data
docker compose --env-file .env.docker up --build -d
```

---

## Local Development Setup

### Prerequisites

- Python 3.13+
- Node.js 22+ (Vite 8 requires Node 22+; Node 26 recommended — matches the Docker build image)
- PostgreSQL 15+ (or use SQLite for quick local work — see Configuration Reference)

### 1. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
SECRET_KEY=<random 256-bit hex string>
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/dmarc
```

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

For quick local work without PostgreSQL, SQLite is also supported:

```
DATABASE_URL=sqlite:///data/dmarc.db
```

### 3. Run Alembic migrations

```bash
alembic upgrade head
```

### 4. Install frontend dependencies

```bash
cd frontend && npm install
```

### 5. Generate an encryption key (for IMAP passwords)

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `.env` as `ENCRYPTION_KEY=`.

### 6. Download GeoIP database (optional)

1. Create a free account at [MaxMind](https://www.maxmind.com/en/geolite2/signup)
2. Download `GeoLite2-City.mmdb`
3. Place it at `data/GeoLite2-City.mmdb`

---

## Running the Stack

Three processes run simultaneously during local development.

**Terminal 1 — API:**

```bash
source .venv/bin/activate
uvicorn api.main:app --reload
```

API: `http://localhost:8000` · Interactive docs: `http://localhost:8000/docs`

**Terminal 2 — File watcher:**

```bash
source .venv/bin/activate
python main.py
```

**Terminal 3 — React frontend:**

```bash
cd frontend && npm run dev
```

UI: `http://localhost:5173`

---

## Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for all schema changes.

**Apply all pending migrations:**

```bash
alembic upgrade head
```

**Generate a migration after changing models:**

```bash
alembic revision --autogenerate -m "short description"
alembic upgrade head
```

**Roll back one migration:**

```bash
alembic downgrade -1
```

**Check current revision:**

```bash
alembic current
```

In Docker, migrations run automatically on every container startup via `docker/entrypoint.sh` before the API server starts, so deployments are always schema-current.

---

## CLI Management

All management tasks:

```bash
# Local
python -m cli.manage <command> [args]

# Docker
docker compose --env-file .env.docker exec api python -m cli.manage <command> [args]
```

| Command | Description |
|---|---|
| `init-db` | Create all tables (equivalent to `alembic upgrade head`, idempotent) |
| `create-client <slug> <name>` | Create a new client and its incoming folder |
| `create-domain <slug> <domain>` | Add a domain to a client |
| `create-user <email> <role> [--client <slug>] [--client-role admin\|viewer]` | Create a user and optionally assign to a client (default per-client role: `viewer`) |
| `set-role <email> <role>` | Change a user's global role (`super_admin` or `user`) |
| `assign-client <email> <slug> [--role admin\|viewer]` | Grant an existing user access to a client (default: `viewer`) |
| `set-client-role <email> <slug> <role>` | Change per-client role for an existing assignment |
| `revoke-client <email> <slug>` | Remove a user's access to a client |
| `reset-password <email> [--temporary]` | Set a new password; `--temporary` forces the user to change it on next login |
| `list-clients` | List all clients |
| `scan <slug> [--dir <path>]` | Manually process all files in a client's incoming folder |
| `enrich-geo <slug> [--force]` | Backfill geo data on records missing location info |
| `enrich-whois <slug> [--force]` | Backfill WHOIS/RDAP ownership data on records missing ASN info |
| `export-client <slug> [--output <path>]` | Export all client data to a ZIP file (JSON/CSV) |
| `purge-client <slug> [--yes]` | Permanently delete all data for a client; prompts for confirmation unless `--yes` |

**Examples:**

```bash
# Create a client
python -m cli.manage create-client acme-corp "Acme Corporation"

# Add a domain
python -m cli.manage create-domain acme-corp mail.acme.com

# Create a super admin (prompted for password)
python -m cli.manage create-user admin@example.com super_admin

# Create a user with admin access to acme-corp
python -m cli.manage create-user manager@acme.com user --client acme-corp --client-role admin

# Create a viewer assigned to acme-corp (default --client-role is viewer)
python -m cli.manage create-user readonly@acme.com user --client acme-corp

# Grant an existing user admin access to a second client
python -m cli.manage assign-client manager@acme.com globex-corp --role admin

# Change a user's per-client role
python -m cli.manage set-client-role readonly@acme.com acme-corp admin

# Reset a user's password (prompted); --temporary forces change on next login
python -m cli.manage reset-password readonly@acme.com --temporary

# Manually process a folder of reports
python -m cli.manage scan acme-corp

# Populate missing geo data after adding the GeoIP database
python -m cli.manage enrich-geo acme-corp
```

---

## Dropping DMARC Reports

DMARC aggregate reports can be delivered in two ways.

### File Drop

Place `.xml.gz` or `.zip` files into the client's incoming directory:

```
data/reports/incoming/{client-slug}/
```

The file watcher processes them automatically within a few seconds. Processed files are archived to:

```
data/reports/archive/{client-slug}/YYYY-MM/
```

Files older than `ARCHIVE_RETENTION_DAYS` (default: 7) are deleted automatically at 02:00 daily.

To process an existing folder of reports immediately:

```bash
python -m cli.manage scan <client-slug>

# Or with a custom path:
python -m cli.manage scan acme-corp --dir /path/to/reports/
```

### IMAP (Automatic Mailbox Polling)

See [IMAP Ingestion](#imap-ingestion) below.

---

## Intelligence Rules

The intelligence engine runs automatically after every report is ingested. It evaluates each record against a set of pluggable rules and stores findings as flags.

### Built-in rules

| Flag type | Severity | Trigger |
|---|---|---|
| `dkim_spf_both_fail` | Critical | Both DKIM and SPF evaluation failed |
| `spf_fail` | High | SPF evaluation failed |
| `dkim_fail` | High | DKIM evaluation failed |
| `policy_mismatch` | Medium | Disposition is `none` but published policy is `quarantine` or `reject` |
| `volume_spike` | Medium | Message count is 5× or more above the historical average for that IP |
| `geo_anomaly` | Medium | Source IP geolocates to a high-risk country (configurable list) |
| `new_sender_ip` | Low | IP address not seen before for this domain |
| `forwarding_pattern` | Info | SPF fail + DKIM pass (classic email forwarding signature) |

### Adding a custom rule

Create a new file in `intelligence/rules/`:

```python
# intelligence/rules/my_rule.py
from sqlalchemy.orm import Session
from core.models import Record
from intelligence.rules.base import BaseRule, FlagResult

class MyRule(BaseRule):
    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        if some_condition(record):
            return [FlagResult(
                flag_type="my_flag",
                severity="medium",
                detail={"reason": "..."},
            )]
        return []
```

Then register it in `intelligence/engine.py`:

```python
from intelligence.rules.my_rule import MyRule

RULES = [
    ...
    MyRule(),
]
```

### Configuring geo risk countries

Edit `HIGH_RISK_COUNTRIES` in `intelligence/rules/geo.py`:

```python
HIGH_RISK_COUNTRIES: set[str] = {
    "KP", "IR", "RU", "CN", "NG", "UA",
}
```

Uses ISO 3166-1 alpha-2 country codes. After changing the list, run `enrich-geo --force` to re-evaluate existing records.

---

## IMAP Ingestion

Each client can have their DMARC reports delivered to a dedicated mailbox and polled automatically.

### Configure via the web UI

1. Go to **Clients** in the sidebar
2. Expand a client card and select the **IMAP** tab
3. Fill in the connection details and click **Save**
4. Use **Test Connection** to verify before enabling
5. Use **Poll Now** to trigger an immediate fetch

### Configure via the API

```bash
curl -X POST http://localhost:8000/clients/acme-corp/imap \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "imap.gmail.com",
    "port": 993,
    "username": "dmarc@acme.com",
    "password": "app-password",
    "use_ssl": true,
    "inbox_folder": "INBOX",
    "processed_folder": "DMARC-Processed",
    "poll_interval_minutes": 15
  }'
```

Processed emails are moved to `processed_folder` (or marked as read if blank). Polling re-syncs within 5 minutes of any config change — no restart needed.

IMAP passwords are encrypted at rest using Fernet symmetric encryption. Set `ENCRYPTION_KEY` in `.env` before saving any credentials.

---

## Adding Clients and Users

### Via CLI

```bash
# Client
python -m cli.manage create-client globex "Globex Corporation"
python -m cli.manage create-domain globex globex.com

# Users — global role is 'user'; per-client role controls what they can do
python -m cli.manage create-user admin@globex.com user --client globex --client-role admin
python -m cli.manage create-user readonly@globex.com user --client globex
```

### Via web UI (super_admin only)

- **Clients page** — create clients, manage domains and IMAP
- **Users page** — create users, edit global and per-client roles, reset passwords

### Azure SSO

Set the following in `.env`:

```
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-app-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_REDIRECT_URI=http://localhost:5173/auth/callback
```

First-time SSO login creates a `user`-role account with no client assignments. A super_admin must assign them to the appropriate client with the correct per-client role via the Users page.

---

## Configuration Reference

All settings are read from the `.env` file (or environment variables in Docker).

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `development` or `production` |
| `SECRET_KEY` | — | JWT signing key — **must be set** |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DATABASE_URL` | `sqlite:///data/dmarc.db` | SQLAlchemy connection URL — use PostgreSQL in production |
| `REPORTS_BASE_DIR` | `data/reports` | Root directory for incoming and archive folders |
| `ARCHIVE_RETENTION_DAYS` | `7` | Days to keep archived report files |
| `ENCRYPTION_KEY` | — | Fernet key for IMAP password encryption — **must be set** |
| `GEOIP_DB_PATH` | `data/GeoLite2-City.mmdb` | Path to MaxMind GeoLite2-City or GeoLite2-Country database |
| `MFA_REQUIRED` | `false` | When `true`, all local accounts must enrol in TOTP MFA before accessing the platform |
| `CLAMAV_ENABLED` | `false` | Enable ClamAV antivirus scanning of ingested files |
| `CLAMAV_HOST` | `localhost` | clamd hostname — use `clamav` when running the Docker Compose service |
| `CLAMAV_PORT` | `3310` | clamd TCP port |
| `CLAMAV_FAIL_OPEN` | `false` | When `false` (default), reject files if clamd is unreachable; when `true`, allow through with a warning |
| `AZURE_TENANT_ID` | — | Azure AD tenant ID (SSO) |
| `AZURE_CLIENT_ID` | — | Azure AD application client ID (SSO) |
| `AZURE_CLIENT_SECRET` | — | Azure AD client secret (SSO) |
| `AZURE_REDIRECT_URI` | `http://localhost:5173/auth/callback` | OAuth2 redirect URI |
| `AZURE_AUTO_PROVISION` | `false` | When `true`, unknown Azure SSO users are auto-created on first login; when `false`, they receive a 403 |
| `API_HOST` | `0.0.0.0` | Bind address for uvicorn |
| `API_PORT` | `8000` | Port for uvicorn |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed CORS origins |
| `ADMIN_EMAIL` | — | Email for the super_admin account created on first boot (seed only) |
| `ADMIN_PASSWORD` | — | Password for the super_admin account created on first boot (seed only) |

**SQLite vs PostgreSQL:** The default `DATABASE_URL` uses SQLite for local development convenience. For production and Docker, use PostgreSQL — changing the URL is all that is required:

```
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/dmarc
```

---

## Project Structure

```
dmarc/
├── .github/
│   ├── dependabot.yml          Automated dependency updates (pip, npm, Docker, Actions, Terraform)
│   └── workflows/
│       ├── deploy.yml          CI/CD — test → build → push to ECR → deploy to AWS via SSM
│       └── deploy-azure.yml    CI/CD — test → build → push to ACR → deploy to Azure via Run Command
├── alembic/                    Alembic migration environment
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_per_client_roles_and_password_reset.py
├── alembic.ini
├── api/                        FastAPI application
│   ├── auth/                   JWT and Azure SSO helpers
│   ├── deps.py                 Auth and DB dependencies (FastAPI Depends)
│   └── routes/                 auth, clients, users, reports, flags, analytics, imap
├── cli/
│   └── manage.py               Management CLI
├── core/
│   ├── config.py               Settings (pydantic-settings, reads .env)
│   ├── crypto.py               Fernet encrypt/decrypt for IMAP credentials
│   ├── database.py             SQLAlchemy engine + SessionLocal + get_db()
│   ├── models/
│   │   └── __init__.py         All models — clients, users, reports, records, flags, auth_results, processed_files
│   ├── schemas/                Pydantic request/response models
│   └── security.py             bcrypt password hashing
├── docker/
│   ├── entrypoint.sh           Container startup: migrations → seed → uvicorn
│   ├── nginx.bootstrap.conf    HTTP-only nginx config for initial certbot certificate acquisition
│   ├── nginx.prod.conf         Production nginx config — HTTPS + ACME passthrough + security headers
│   └── seed.py                 Idempotent first-boot seed (admin user + test client)
├── docs/                       Documentation
│   ├── deployment-guide.md     Full production deployment guide (Terraform, CI/CD, certbot, backups)
│   ├── developer-guide.md
│   ├── admin-guide.md
│   └── user-guide.md
├── frontend/                   React + Vite application
│   ├── src/
│   │   ├── api/                Axios API clients
│   │   ├── components/         Layout, UI primitives, shared components
│   │   ├── contexts/           AuthContext, ClientContext
│   │   └── pages/              Login, ChangePassword, Dashboard, Reports, Flags, Analytics, Clients, Users
│   ├── Dockerfile              Multi-stage: Node build → nginx serve
│   └── nginx.conf              nginx config (SPA routing + /api proxy, dev/Docker only)
├── ingestion/
│   ├── extractor.py            Decompress .gz and .zip files
│   ├── geo_enrichment.py       Retroactively populate geo fields on existing records
│   ├── imap_fetcher.py         IMAP connection and attachment extraction
│   ├── parser.py               DMARC XML → Python dataclasses
│   ├── pipeline.py             Orchestrates extract → parse → write → flag
│   ├── scanner.py              ClamAV antivirus integration (optional)
│   ├── scheduler.py            APScheduler (archive purge + IMAP polling)
│   ├── watcher.py              watchdog file system observer
│   └── writer.py               Persist parsed reports to the database
├── intelligence/
│   ├── engine.py               Runs all rules; stores Flag records
│   └── rules/                  base, auth, geo, senders, volume (pluggable)
├── terraform/
│   ├── aws/                    AWS infrastructure (VPC, EC2, ECR, IAM, RDS)
│   │   ├── main.tf             Root module — wires networking, security, registry, iam, compute, database
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── terraform.tfvars.example
│   │   └── modules/
│   │       ├── networking/     VPC, subnets, IGW, NAT Gateway, route tables
│   │       ├── security/       App and DB security groups
│   │       ├── compute/        EC2, Elastic IP, key pair
│   │       ├── registry/       ECR repositories + lifecycle policies
│   │       ├── iam/            EC2 instance profile (ECR pull + SSM access), CI user
│   │       └── database/       DB EC2 (split_vm) or RDS PostgreSQL (split_managed)
│   └── azure/                  Azure infrastructure (VNet, VM, ACR, Managed Identity, PostgreSQL)
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── terraform.tfvars.example
│       └── modules/
│           ├── networking/     VNet, subnets, NAT Gateway, delegated subnet
│           ├── security/       App and DB NSGs
│           ├── compute/        VM, static public IP, NIC
│           ├── registry/       Azure Container Registry
│           ├── iam/            User-assigned Managed Identity + AcrPull role
│           └── database/       DB VM (split_vm) or PostgreSQL Flexible Server (split_managed)
├── tests/                      pytest test suite
├── .env.example                Local development environment template
├── .env.docker                 Docker functional-test environment
├── .env.prod.example           Production environment template
├── docker-compose.yml          Dev/test stack: PostgreSQL, API, watcher, frontend
├── docker-compose.prod.yml     Production stack: ECR/ACR images, certbot, ClamAV
├── docker-compose.bootstrap.yml One-time SSL bootstrap override (HTTP-only nginx for certbot)
├── Dockerfile                  Python backend image
├── geoip/                      Place GeoLite2-City.mmdb here (not committed)
├── main.py                     File watcher + scheduler entry point
└── requirements.txt            Python dependencies
```

---

## License

Copyright (C) 2026 Matt Comeione

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

The full license text is in the [LICENSE](LICENSE) file. You can also read it at
<https://www.gnu.org/licenses/agpl-3.0.html>.

**What this means in practice:** Anyone who runs a modified version of this
software over a network (e.g. as a hosted service) must make their modified
source code available to users of that service under the same license.

---

## Third-Party Attributions

### MaxMind GeoLite2

This product includes GeoLite2 data created by MaxMind, available from
<https://www.maxmind.com>.

The GeoLite2 database is **not** bundled in this repository. Users must
download it directly from MaxMind under the
[GeoLite2 End User License Agreement](https://www.maxmind.com/en/geolite2/eula).
A free MaxMind account is required. See [Enable GeoIP detection](#4-enable-geoip-detection-optional)
in the Quick Start section for setup instructions.

### Python dependencies

Key backend libraries and their licenses:

| Package | License | Project |
|---------|---------|---------|
| FastAPI | MIT | <https://fastapi.tiangolo.com> |
| SQLAlchemy | MIT | <https://www.sqlalchemy.org> |
| Alembic | MIT | <https://alembic.sqlalchemy.org> |
| Pydantic | MIT | <https://docs.pydantic.dev> |
| psycopg2 | LGPL-3.0 | <https://www.psycopg.org> |
| cryptography | Apache-2.0 / BSD | <https://cryptography.io> |
| PyJWT | MIT | <https://pyjwt.readthedocs.io> |
| bcrypt | Apache-2.0 | <https://github.com/pyca/bcrypt> |
| defusedxml | PSFL | <https://github.com/tiran/defusedxml> |
| geoip2 | Apache-2.0 | <https://github.com/maxmind/GeoIP2-python> |
| watchdog | Apache-2.0 | <https://github.com/gorakhargosh/watchdog> |
| APScheduler | MIT | <https://apscheduler.readthedocs.io> |
| slowapi | MIT | <https://github.com/laurentS/slowapi> |
| pyotp | MIT | <https://github.com/pyauth/pyotp> |
| msal | MIT | <https://github.com/AzureAD/microsoft-authentication-library-for-python> |
| imapclient | BSD-3-Clause | <https://imapclient.readthedocs.io> |
| ipwhois | BSD | <https://github.com/secynic/ipwhois> |
| dnspython | ISC | <https://www.dnspython.org> |
| Faker | MIT | <https://faker.readthedocs.io> |
| python-clamd | LGPL-2.1 | <https://github.com/graingert/python-clamd> (optional — required only when `CLAMAV_ENABLED=true`) |

### Frontend dependencies

| Package | License | Project |
|---------|---------|---------|
| React | MIT | <https://react.dev> |
| React Router | MIT | <https://reactrouter.com> |
| TanStack Query | MIT | <https://tanstack.com/query> |
| Vite | MIT | <https://vitejs.dev> |
| Tailwind CSS | MIT | <https://tailwindcss.com> |
| Recharts | MIT | <https://recharts.org> |
| Lucide React | ISC | <https://lucide.dev> |
| Axios | MIT | <https://axios-http.com> |
| world-atlas | ISC | <https://github.com/topojson/world-atlas> |