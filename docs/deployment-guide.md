# DMARC Intelligence Platform — Deployment Guide

*Ubuntu 24.04 LTS — Single-server Docker deployment*

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [System Preparation](#system-preparation)
4. [Install Docker and Docker Compose](#install-docker-and-docker-compose)
5. [Firewall Configuration](#firewall-configuration)
6. [Clone the Application](#clone-the-application)
7. [Configure the Environment](#configure-the-environment)
8. [GeoIP Database](#geoip-database)
9. [First Start](#first-start)
10. [Nginx Reverse Proxy](#nginx-reverse-proxy)
11. [SSL Certificate](#ssl-certificate)
12. [Initial Setup via CLI](#initial-setup-via-cli)
13. [Automated Backups](#automated-backups)
14. [Ongoing Operations](#ongoing-operations)
15. [Updating the Application](#updating-the-application)
16. [Troubleshooting](#troubleshooting)

---

## Overview

This guide walks through deploying the DMARC Intelligence Platform to a fresh Ubuntu 24.04 LTS server. The platform runs as four Docker containers behind a host-level nginx reverse proxy with a Let's Encrypt SSL certificate.

```
Internet
    │  HTTPS :443
    ▼
┌─────────────────────────────────────┐
│  nginx (host process)               │
│  Terminates TLS, proxies to :5010   │
└────────────────┬────────────────────┘
                 │  HTTP :5010
    ┌────────────▼────────────────────────────────┐
    │  Docker network (internal bridge)            │
    │                                              │
    │  ┌─────────────┐    ┌─────────────────────┐ │
    │  │  frontend   │    │       api           │ │
    │  │  nginx:5010 │───▶│  uvicorn:8000       │ │
    │  │  React SPA  │    │  FastAPI + Alembic  │ │
    │  └─────────────┘    └──────────┬──────────┘ │
    │                                │             │
    │  ┌─────────────┐    ┌──────────▼──────────┐ │
    │  │   watcher   │    │        db           │ │
    │  │  File watch │    │  PostgreSQL 16      │ │
    │  │  IMAP poll  │    │  port 5432 internal │ │
    │  └─────────────┘    └─────────────────────┘ │
    └─────────────────────────────────────────────┘
```

**Port exposure:** Only port 5010 (frontend container) is accessible from the host. Ports 8000 (API) and 5432 (database) are internal to the Docker network only. The host's nginx proxies external HTTPS traffic to port 5010.

**Data persistence:** PostgreSQL data and report files are stored in `./docker-data/` as Docker bind mounts. GeoIP databases are stored in `./geoip/` and are never wiped by reset operations.

---

## Prerequisites

Before starting, ensure you have:

- [ ] A fresh Ubuntu 24.04 LTS server with root or sudo access
- [ ] A registered domain name with an **A record** pointing to the server's public IP (e.g. `dmarc.example.com → 203.0.113.10`)
  - DNS propagation must complete before the SSL certificate step
- [ ] Ports **80** and **443** open inbound from the internet
- [ ] SSH access to the server
- [ ] (Optional but recommended) A free MaxMind account for GeoIP data: https://www.maxmind.com/en/geolite2/signup
- [ ] (Optional) An Azure AD app registration if you plan to use Microsoft 365 OAuth2 IMAP or Azure SSO

### Recommended server sizing

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 2–4 vCPU |
| RAM | 4 GB | 4–8 GB |
| Disk | 50 GB | 100 GB |
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |

Disk usage grows with the number of clients and volume of DMARC reports. Monitor with `df -h /` and expand the volume before it reaches 80% capacity.

---

## System Preparation

Update the system and install required packages:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw nginx python3-certbot-nginx
```

Create a dedicated non-root user to own the application files. This user will run all Docker commands:

```bash
sudo useradd -m -s /bin/bash dmarc
sudo usermod -aG sudo dmarc
```

Switch to the new user for all remaining steps:

```bash
sudo su - dmarc
```

---

## Install Docker and Docker Compose

Use the official Docker installation script (this installs Docker Engine and the Compose plugin):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

> **Important:** Log out and back in (or run `newgrp docker`) for the group membership to take effect. Verify:

```bash
docker --version
docker compose version
```

Expected output (versions may differ):
```
Docker version 27.x.x, build ...
Docker Compose version v2.x.x
```

---

## Firewall Configuration

Configure ufw to allow only SSH and web traffic:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Verify:

```bash
sudo ufw status
```

Expected output:
```
Status: active

To                         Action      From
--                         ------      ----
OpenSSH                    ALLOW       Anywhere
Nginx Full                 ALLOW       Anywhere
```

> **Do not** add rules for port 8000 (API) or 5432 (PostgreSQL). These ports must remain inaccessible from the internet.

---

## Clone the Application

Create the application directory and clone the repository:

```bash
sudo mkdir -p /opt/dmarc
sudo chown dmarc:dmarc /opt/dmarc
git clone <repository-url> /opt/dmarc/app
cd /opt/dmarc/app
```

Replace `<repository-url>` with your actual repository URL.

Create the data directories referenced by Docker Compose:

```bash
mkdir -p /opt/dmarc/app/geoip
mkdir -p /opt/dmarc/backups
```

---

## Configure the Environment

Copy the example environment file and edit it:

```bash
cd /opt/dmarc/app
cp .env.docker.example .env.docker
nano .env.docker
```

### Required values

**1. Generate `SECRET_KEY`**

This key signs all JWT tokens. Any long random string works — generate one:

```bash
openssl rand -hex 32
```

Paste the output as the value of `SECRET_KEY`.

**2. Generate `ENCRYPTION_KEY`**

This key encrypts IMAP passwords stored in the database. It must be a Fernet-format key (32 URL-safe base64 bytes):

```bash
docker run --rm python:3.13-slim python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output as the value of `ENCRYPTION_KEY`.

> **Keep both keys safe.** Loss of `ENCRYPTION_KEY` means stored IMAP credentials cannot be decrypted. Back these keys up securely (e.g. a password manager). Never commit `.env.docker` to version control.

**3. Set `ADMIN_PASSWORD`**

Set a strong initial password for the super\_admin account. You will be prompted to change it on first login.

**4. Set `CORS_ORIGINS`**

Change to your public domain:

```
CORS_ORIGINS=https://dmarc.example.com
```

**5. Set `AZURE_REDIRECT_URI` (if using Azure SSO)**

```
AZURE_REDIRECT_URI=https://dmarc.example.com/auth/callback
```

**6. Set `MFA_REQUIRED` (optional)**

Set to `true` to require all local accounts to enrol in TOTP MFA before accessing the platform. super\_admin accounts always require MFA regardless of this setting.

```
MFA_REQUIRED=false
```

### Final `.env.docker` checklist

Before continuing, confirm these values are set:

- [ ] `SECRET_KEY` — non-empty
- [ ] `ENCRYPTION_KEY` — non-empty, Fernet format
- [ ] `ADMIN_EMAIL` — your super\_admin email address
- [ ] `ADMIN_PASSWORD` — a strong password
- [ ] `CORS_ORIGINS` — your public HTTPS domain
- [ ] `MFA_REQUIRED` — set to `true` if you want to enforce MFA for all users from day one (recommended for production)

---

## GeoIP Database

The GeoIP database enables country, city, and region enrichment on DMARC records and powers the world map visualisation. Without it, the platform starts normally but geo-anomaly flagging and location data are disabled.

1. Sign up at https://www.maxmind.com/en/geolite2/signup
2. Download **GeoLite2-City.mmdb** (provides country, city, region, and coordinates)
3. Upload the file to your server:

```bash
scp GeoLite2-City.mmdb dmarc@your-server:/opt/dmarc/app/geoip/
```

Or download directly on the server using the MaxMind download link from your account page.

The GeoIP database is mounted read-only into the containers at `/app/geoip/`. It is separate from `docker-data/` and survives all reset operations.

**Keeping GeoIP up to date:** MaxMind updates GeoLite2 databases weekly. Set up a monthly cron job or use the MaxMind GeoIP Update tool (`geoipupdate`) to keep the database current.

---

## ClamAV Antivirus Scanning (Optional)

ClamAV scanning is disabled by default. When enabled, every ingested DMARC report file — whether dropped via the filesystem or received via IMAP — is scanned by the ClamAV daemon (`clamd`) before decompression. Infected files are rejected with a `[SECURITY] MALWARE DETECTED` log entry and never written to the database.

This feature is recommended for deployments that receive reports from a broad range of external senders or operate under a security compliance requirement (SOC 2, ISO 27001, etc.).

### 1. Install ClamAV

```bash
sudo apt-get update
sudo apt-get install -y clamav clamav-daemon
```

### 2. Download the virus database (one-time)

```bash
sudo systemctl stop clamav-freshclam
sudo freshclam
sudo systemctl start clamav-freshclam
```

This downloads ~300 MB of signature data. Allow 2–5 minutes.

### 3. Configure clamd to listen on TCP

Edit `/etc/clamav/clamd.conf` and add or uncomment:

```
TCPSocket 3310
TCPAddr 127.0.0.1
```

Then restart the daemon:

```bash
sudo systemctl restart clamav-daemon
sudo systemctl enable clamav-daemon
```

Verify clamd is accepting connections:

```bash
echo PING | nc 127.0.0.1 3310
# Expected output: PONG
```

### 4. Enable scanning in .env.docker

```bash
CLAMAV_ENABLED=true
CLAMAV_HOST=127.0.0.1   # or "clamav" if using the Docker Compose service
CLAMAV_PORT=3310
CLAMAV_FAIL_OPEN=false  # recommended: reject file if clamd is unreachable
```

### 5. Docker Compose deployment

For Docker-based deployments, an optional ClamAV service is provided as commented-out blocks in `docker-compose.yml`. To enable it:

1. Uncomment the `clamav` service and `clamav-data` volume in `docker-compose.yml`
2. Set `CLAMAV_HOST=clamav` in `.env.docker` (the Docker service name)
3. Set `CLAMAV_ENABLED=true` in `.env.docker`
4. Rebuild and start:

```bash
docker compose --env-file .env.docker up --build -d
```

> **First-boot note:** freshclam must download the virus database (~300 MB) before clamd starts accepting connections. The `start_period: 300s` healthcheck gives it time. API and watcher containers wait for clamd to be healthy before starting.

### 6. CLAMAV_FAIL_OPEN — fail closed vs fail open

| Setting | Behaviour when clamd is unreachable | Use when |
|---------|-------------------------------------|----------|
| `CLAMAV_FAIL_OPEN=false` (default) | File is **rejected** — `[SECURITY]` ERROR logged | Compliance/regulated environments — security over availability |
| `CLAMAV_FAIL_OPEN=true` | File is **allowed through** — `[SECURITY]` WARNING logged | Report continuity is more important than blocking during clamd downtime |

### 7. Keeping signatures up to date

`freshclam` should run daily. On Ubuntu with the default package install this is handled automatically by the `clamav-freshclam` service. Verify:

```bash
sudo systemctl status clamav-freshclam
```

In Docker, the official `clamav/clamav:stable` image runs freshclam automatically. The `clamav-data` volume persists the database between container restarts so it is not re-downloaded on each start.

---

## First Start

Start the full stack:

```bash
cd /opt/dmarc/app
docker compose --env-file .env.docker up --build -d
```

The `--build` flag builds all images on first run. Subsequent starts do not need `--build` unless the code has changed.

Monitor the API startup to confirm migrations and seeding complete successfully:

```bash
docker compose logs api -f --tail 50
```

Expected output sequence:
```
api-1  | ==> Running Alembic migrations...
api-1  | INFO  [alembic.runtime.migration] Running upgrade ...
api-1  | ==> Seeding initial data...
api-1  |   Created super_admin: admin@example.com
api-1  |   Created test client: test-client
api-1  | ==> Starting API server on :8000...
api-1  | INFO:     Application startup complete.
```

Press `Ctrl+C` to stop following the logs. The containers continue running.

Verify all containers are healthy:

```bash
docker compose ps
```

All services should show `healthy` or `running`. If `api` shows `unhealthy`, check the logs.

Test the API directly:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok", "version": "0.2.0"}
```

---

## Nginx Reverse Proxy

Create the nginx site configuration:

```bash
sudo nano /etc/nginx/sites-available/dmarc
```

Paste the following (replace `dmarc.example.com` with your domain):

```nginx
server {
    listen 80;
    server_name dmarc.example.com;

    location / {
        proxy_pass http://127.0.0.1:5010;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Increase timeouts for large report uploads
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

Enable the site and verify the configuration:

```bash
sudo ln -s /etc/nginx/sites-available/dmarc /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
```

Expected: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

Reload nginx:

```bash
sudo systemctl reload nginx
```

Test that the site is reachable over HTTP before proceeding to SSL:

```bash
curl -I http://dmarc.example.com
```

You should receive an HTTP response (200 or 302).

---

## SSL Certificate

Obtain a certificate from Let's Encrypt. Certbot will modify the nginx configuration to add SSL and set up automatic HTTP → HTTPS redirection:

```bash
sudo certbot --nginx -d dmarc.example.com
```

Follow the prompts (agree to terms, enter an email for expiry notifications). Certbot will:
1. Validate domain ownership via HTTP (port 80 must be open)
2. Obtain the certificate
3. Modify `/etc/nginx/sites-available/dmarc` to add SSL configuration
4. Reload nginx

Verify HTTPS is working:

```bash
curl -I https://dmarc.example.com
```

Verify automatic renewal is configured:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

The dry run should succeed without errors. Certbot renews certificates automatically when they have less than 30 days remaining.

---

## Initial Setup via CLI

The seed script creates one super\_admin and one test client on first boot. Use the CLI to set up your actual clients and users.

> **First login — MFA enrolment required:** The super\_admin account always requires MFA. When you sign in for the first time you will be redirected to the MFA setup page before you can access any other page. Open your authenticator app (Microsoft Authenticator, Authy, or Google Authenticator), scan the QR code, enter the 6-digit confirmation code, and click **Enable MFA**. Subsequent logins will ask for the code after your password.

All CLI commands are run inside the `api` container:

```bash
docker compose --env-file .env.docker exec api python -m cli.manage <command>
```

### MSP setup example

```bash
# Create a client for each customer
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-client acme-corp "Acme Corporation"

# Add the customer's sending domain
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-domain acme-corp mail.acme-corp.com

# Create a viewer account for the customer's stakeholder
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-user stakeholder@acme-corp.com user --client acme-corp --client-role viewer

# Create an admin account for your team member managing this client
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-user engineer@yourcompany.com user --client acme-corp --client-role admin
```

### Single-tenant setup example

```bash
# Create the company client
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-client my-company "My Company Ltd"

# Add the primary sending domain
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-domain my-company mail.mycompany.com

# Create an admin for the IT team
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-user it-admin@mycompany.com user --client my-company --client-role admin

# Create a viewer for a junior team member
docker compose --env-file .env.docker exec api python -m cli.manage \
  create-user junior@mycompany.com user --client my-company --client-role viewer
```

### Full CLI reference

| Command | Description |
|---------|-------------|
| `create-client <slug> <name>` | Create a client and its incoming report folder |
| `create-domain <slug> <domain>` | Add a domain to a client |
| `create-user <email> <role> [--client <slug>] [--client-role admin\|viewer]` | Create a user |
| `set-role <email> <role>` | Change global role (`super_admin` or `user`) |
| `assign-client <email> <slug> [--role admin\|viewer]` | Add a client assignment to an existing user |
| `set-client-role <email> <slug> <role>` | Change per-client role |
| `revoke-client <email> <slug>` | Remove a client assignment |
| `reset-password <email> [--temporary]` | Set a new password |
| `list-clients` | List all clients |
| `scan <slug>` | Manually process all files in the client's incoming folder |
| `enrich-geo <slug> [--force]` | Backfill geolocation data on existing records |
| `export-client <slug> [--output <path>]` | Export all client data to a ZIP file (JSON/CSV) |
| `purge-client <slug> [--yes]` | Permanently delete all data for a client |

---

## Automated Backups

Set up a daily PostgreSQL backup using a systemd timer.

### Backup script

Create the script at `/opt/dmarc/backup.sh`:

```bash
sudo nano /opt/dmarc/backup.sh
```

```bash
#!/bin/bash
set -euo pipefail

APP_DIR="/opt/dmarc/app"
BACKUP_DIR="/opt/dmarc/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

mkdir -p "$BACKUP_DIR"

docker compose -f "$APP_DIR/docker-compose.yml" \
    --env-file "$APP_DIR/.env.docker" \
    exec -T db pg_dump -U dmarc dmarc \
    | gzip > "$BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"

# Remove backups older than RETAIN_DAYS days
find "$BACKUP_DIR" -name "dmarc_*.sql.gz" -mtime +"$RETAIN_DAYS" -delete

echo "Backup complete: $BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"
```

Make it executable:

```bash
sudo chmod +x /opt/dmarc/backup.sh
sudo chown dmarc:dmarc /opt/dmarc/backup.sh
```

### systemd service

Create `/etc/systemd/system/dmarc-backup.service`:

```bash
sudo nano /etc/systemd/system/dmarc-backup.service
```

```ini
[Unit]
Description=DMARC Platform Database Backup
Wants=dmarc-backup.timer

[Service]
Type=oneshot
User=dmarc
ExecStart=/opt/dmarc/backup.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### systemd timer

Create `/etc/systemd/system/dmarc-backup.timer`:

```bash
sudo nano /etc/systemd/system/dmarc-backup.timer
```

```ini
[Unit]
Description=Run DMARC database backup daily at 03:00
Requires=dmarc-backup.service

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### Enable and verify

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dmarc-backup.timer
sudo systemctl list-timers dmarc-backup.timer
```

Test a manual backup immediately:

```bash
sudo systemctl start dmarc-backup.service
journalctl -u dmarc-backup.service -n 20
ls -lh /opt/dmarc/backups/
```

### Restore procedure

```bash
# 1. Stop the application (keep the database running)
cd /opt/dmarc/app
docker compose --env-file .env.docker stop api watcher frontend

# 2. Drop and recreate the public schema
docker compose --env-file .env.docker exec -T db \
  psql -U dmarc -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3. Restore from backup
gunzip -c /opt/dmarc/backups/dmarc_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose --env-file .env.docker exec -T db psql -U dmarc dmarc

# 4. Restart the application
docker compose --env-file .env.docker up -d
```

> **Off-site backup:** Copy backup files to a remote location (S3, another server, etc.) using `rclone` or `rsync`. A local-only backup does not protect against server loss.

---

## Ongoing Operations

### Viewing logs

```bash
# API logs (migrations, requests, errors)
docker compose logs api -f --tail 100

# File watcher and IMAP poller logs
docker compose logs watcher -f --tail 100

# All containers
docker compose logs -f
```

### Checking container status

```bash
docker compose ps
```

### Restarting a container

```bash
docker compose restart api
docker compose restart watcher
```

### Dropping a DMARC report manually

Place `.xml.gz` or `.zip` DMARC report files in the client's incoming folder:

```bash
cp report.xml.gz /opt/dmarc/app/docker-data/reports/incoming/acme-corp/
```

The watcher container picks it up within seconds.

### Running CLI commands

```bash
docker compose --env-file .env.docker exec api python -m cli.manage <command>
```

### Stopping and starting the stack

```bash
# Stop (data persists in docker-data/)
docker compose down

# Start again
docker compose --env-file .env.docker up -d
```

### Monitoring disk usage

```bash
# Overall disk
df -h /

# Docker-specific usage
docker system df

# Application data
du -sh /opt/dmarc/app/docker-data/
du -sh /opt/dmarc/backups/
```

---

## Updating the Application

```bash
cd /opt/dmarc/app

# Pull the latest code
git pull

# Rebuild and restart — migrations run automatically on startup
docker compose --env-file .env.docker up --build -d
```

Watch the API logs to confirm migrations completed:

```bash
docker compose logs api --tail 30
```

To rebuild only the frontend (e.g. after a UI-only change):

```bash
docker compose --env-file .env.docker up --build -d frontend
```

> **Always take a backup before updating** if the update includes database migrations.

---

## Troubleshooting

### Container fails to start

```bash
docker compose logs api --tail 50
```

Common causes:
- Missing or invalid `SECRET_KEY` or `ENCRYPTION_KEY` — check `.env.docker`
- Database connection failure — verify `DATABASE_URL` credentials match `docker-compose.yml`
- Port conflict — check no other process is using port 5010 (`sudo ss -tlnp | grep 5010`)

### "Validation error" on startup

Pydantic settings failed to load. Check that `SECRET_KEY` and `ENCRYPTION_KEY` are both set and non-empty in `.env.docker`.

### 502 Bad Gateway from nginx

The API or frontend container is not yet healthy. Wait 30 seconds and retry. If it persists:

```bash
docker compose ps
docker compose logs api --tail 20
```

### Can't reach the site at all

```bash
sudo systemctl status nginx
sudo ufw status
curl http://localhost:5010  # test directly without nginx
```

### Login appears to succeed but the page doesn't change

The login request returned 200 OK, but the `/auth/me` call immediately after is returning 403. This means the access token contains `msr=True` (MFA setup required) and the middleware is blocking `/auth/me`.

Check that the API was rebuilt after the latest code changes and that the middleware exempt paths in `api/main.py` match the actual FastAPI route paths (they should be `/auth/me`, not `/api/auth/me`):

```bash
docker compose --env-file .env.docker up --build -d api
docker compose logs api --tail 20
```

If the admin account doesn't have MFA enrolled yet, signing in will redirect to the MFA setup page — this is expected behaviour, not an error. Complete the enrolment to proceed.

### MFA QR code not showing

```bash
docker compose logs api --tail 20
```

Look for `ModuleNotFoundError: No module named 'PIL'`. This means the image was built before `qrcode[pil]` was added to requirements. Rebuild:

```bash
docker compose --env-file .env.docker up --build -d api
```

### Reports not being processed

```bash
docker compose logs watcher --tail 50
```

Verify the incoming directory exists and contains the report file:

```bash
ls /opt/dmarc/app/docker-data/reports/incoming/acme-corp/
```

The client slug in the directory name must exactly match the slug in the database.

### IMAP polling errors

Check the last poll status in the web UI (Clients → Mail Ingestion tab). Check the watcher logs:

```bash
docker compose logs watcher --tail 30
```

Common causes: expired credentials, changed mailbox name, network firewall blocking outbound port 993.

### Database full or slow

```bash
# Connect to the database
docker compose --env-file .env.docker exec db psql -U dmarc dmarc

-- Check table sizes
SELECT relname AS table,
       pg_size_pretty(pg_total_relation_size(oid)) AS size
FROM pg_class
WHERE relkind = 'r'
ORDER BY pg_total_relation_size(oid) DESC
LIMIT 10;
```

The `records` and `auth_results` tables grow the fastest. Archive retention (default 7 days for report files) does not delete database records. Purging old records requires a manual database operation — contact your platform developer.

### SSL certificate renewal failure

```bash
sudo certbot renew --dry-run
sudo journalctl -u certbot -n 50
```

Ensure port 80 is open to the internet (`sudo ufw status`, check firewall at your cloud provider).