# DMARC Intelligence Platform — Deployment Guide

*Ubuntu 24.04 LTS — Single-server Docker deployment with CI/CD*

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Provision Infrastructure with Terraform](#provision-infrastructure-with-terraform)
4. [Configure GitHub Actions CI/CD](#configure-github-actions-cicd)
5. [First-Time Server Setup](#first-time-server-setup)
6. [Configure the Environment](#configure-the-environment)
7. [GeoIP Database](#geoip-database)
8. [SSL Certificate with Certbot (Docker)](#ssl-certificate-with-certbot-docker)
9. [First Deployment](#first-deployment)
10. [Initial Application Setup via CLI](#initial-application-setup-via-cli)
11. [Automated Certificate Renewal](#automated-certificate-renewal)
12. [Automated Backups](#automated-backups)
13. [Ongoing Operations](#ongoing-operations)
14. [Updating the Application](#updating-the-application)
15. [Troubleshooting](#troubleshooting)

---

## Overview

The DMARC Intelligence Platform runs as six Docker containers managed by Docker Compose. In production, the frontend container handles TLS directly — no host-level reverse proxy is required.

```
Internet
    │  HTTPS :443 / HTTP :80
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Docker network (dmarc-prod)                                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  frontend (nginx)  :80 :443                              │   │
│  │  - HTTP :80  → ACME challenge or 301 redirect to HTTPS  │   │
│  │  - HTTPS :443 → serves React SPA, proxies /api/*        │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │                                      │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │  api  (FastAPI / uvicorn :8000)                          │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │                                      │
│  ┌───────────┐  ┌────────▼──────────┐  ┌───────────────────┐   │
│  │  watcher  │  │  db (PostgreSQL)  │  │  certbot          │   │
│  │  + sched  │  │  :5432 internal   │  │  renewal loop     │   │
│  └───────────┘  └───────────────────┘  └───────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  clamav (clamd :3310 internal)                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Port exposure:** The frontend container binds ports 80 and 443 on the host. Ports 8000 (API), 5432 (PostgreSQL), and 3310 (ClamAV) are internal to the Docker network only.

**Image delivery:** Container images are built by GitHub Actions, pushed to Amazon ECR, and pulled to the server on each deployment. The server never builds images locally.

---

## Prerequisites

Before starting, ensure you have:

- [ ] Terraform ≥ 1.5 installed locally
- [ ] AWS CLI configured with credentials that can create VPCs, EC2, ECR, and IAM resources
- [ ] A registered domain name — DNS will be pointed to the server's Elastic IP after provisioning
- [ ] An SSH key pair on your local machine (`~/.ssh/id_rsa` and `~/.ssh/id_rsa.pub`)
- [ ] A GitHub repository containing the application code
- [ ] (Optional) A free MaxMind account for GeoIP data

### Server sizing with ClamAV

| Resource | Without ClamAV | **With ClamAV (default)** |
|----------|---------------|--------------------------|
| CPU | 2 vCPU | **2 vCPU** |
| RAM | 4 GB (t3.medium) | **8 GB (t3.large)** |
| Disk | 50 GB | **100 GB** |

ClamAV loads 700 MB–1 GB of virus signatures into RAM at startup. The Terraform configuration auto-selects `t3.large` when `clamav_enabled = true`.

---

## Provision Infrastructure with Terraform

The Terraform configuration in `terraform/aws/` provisions all required AWS infrastructure using the naming convention `{project}-{environment}-{resource}` (e.g. `dmarc-prod-vpc`).

### Resources created

| Resource | Name |
|---|---|
| VPC | `dmarc-prod-vpc` |
| Internet Gateway | `dmarc-prod-igw` |
| Public Subnet | `dmarc-prod-public-subnet` |
| Route Table | `dmarc-prod-public-rt` |
| Security Group | `dmarc-prod-app-sg` |
| EC2 Instance | `dmarc-prod-app-ec2` |
| Elastic IP | `dmarc-prod-eip` |
| Key Pair | `dmarc-prod-keypair` |
| ECR Repository (API) | `dmarc-prod-api` |
| ECR Repository (Frontend) | `dmarc-prod-frontend` |
| IAM Role | `dmarc-prod-ec2-role` |
| IAM Instance Profile | `dmarc-prod-ec2-profile` |

### Security group rules

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 443 | TCP | `0.0.0.0/0` | HTTPS |
| 80 | TCP | `0.0.0.0/0` | HTTP (ACME + redirect) |
| 22 | TCP | `admin_cidr` | SSH (your IP only) |
| 22 | TCP | `cicd_cidr` | SSH for CI/CD (optional) |

### Deploy

```bash
cd terraform/aws
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` — at minimum set:
- `admin_cidr` — your current public IP as `x.x.x.x/32`  
  *(find it: `curl -s https://checkip.amazonaws.com`)*
- `ssh_public_key_path` — path to your `.pub` file (default `~/.ssh/id_rsa.pub`)

Then:

```bash
terraform init
terraform plan
terraform apply
```

After `apply` completes, note these outputs — you will need them shortly:

```bash
terraform output public_ip          # Point your DNS A record here
terraform output instance_id        # Store as GitHub secret EC2_INSTANCE_ID
terraform output ecr_registry_url   # Store as GitHub secret ECR_REGISTRY
terraform output ecr_api_repo       # Store as GitHub secret ECR_API_REPO
terraform output ecr_frontend_repo  # Store as GitHub secret ECR_FRONTEND_REPO
```

### CI/CD IAM credentials

The EC2 instance IAM profile allows it to pull from ECR without credentials. For the GitHub Actions *build and push* step you need a separate IAM user or OIDC role with ECR push access.

**Option A — Dedicated IAM user (simpler)**

Set `create_ci_user = true` in `terraform.tfvars` and re-run `terraform apply`. Retrieve the credentials:

```bash
terraform output ci_user_access_key_id
terraform output -raw ci_user_secret_access_key
```

Store these as GitHub secrets `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

**Option B — GitHub Actions OIDC (recommended — no long-lived secrets)**

Follow the GitHub documentation to configure OIDC for AWS:
https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services

Update `.github/workflows/deploy.yml` to use `role-to-assume` instead of access key secrets.

---

## Configure GitHub Actions CI/CD

In your GitHub repository go to **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | From Terraform output or OIDC role |
| `AWS_SECRET_ACCESS_KEY` | From Terraform output or OIDC role |
| `ECR_REGISTRY` | From `terraform output ecr_registry_url` |
| `ECR_API_REPO` | From `terraform output ecr_api_repo` |
| `ECR_FRONTEND_REPO` | From `terraform output ecr_frontend_repo` |
| `EC2_INSTANCE_ID` | From `terraform output instance_id` |

The workflow (`.github/workflows/deploy.yml`) runs on every push to `main`:

1. **Test** — builds the API image and runs the full pytest suite
2. **Build & Push** — builds API and frontend images, tags with the 8-char git SHA, pushes to ECR
3. **Deploy** — uses AWS SSM to run the deployment commands on the EC2 instance (no SSH port needs to be open to GitHub runner IPs)

> **SSM deployment:** The EC2 IAM role includes `AmazonSSMManagedInstanceCore`. GitHub Actions uses `aws ssm send-command` to trigger a deployment on the instance and waits for completion. The full deployment log appears in the Actions run.

---

## First-Time Server Setup

SSH into the server using the key pair you provided:

```bash
ssh -i ~/.ssh/id_rsa ubuntu@$(terraform -chdir=terraform/aws output -raw public_ip)
```

Docker was installed by the EC2 `user_data` script. Verify it is running:

```bash
docker --version
docker compose version
```

Create the application directory and copy the required files from the repository:

```bash
sudo mkdir -p /opt/dmarc/geoip
sudo chown ubuntu:ubuntu /opt/dmarc
```

Copy from your local machine (or clone the repo on the server for the config files only):

```bash
# From your local machine:
scp -i ~/.ssh/id_rsa \
  docker-compose.prod.yml \
  docker-compose.bootstrap.yml \
  .env.prod.example \
  ubuntu@<public_ip>:/opt/dmarc/

scp -i ~/.ssh/id_rsa \
  docker/nginx.prod.conf \
  docker/nginx.bootstrap.conf \
  ubuntu@<public_ip>:/opt/dmarc/docker/
```

Or clone the full repository and work from `/opt/dmarc`:

```bash
git clone <repository-url> /opt/dmarc
cd /opt/dmarc
```

---

## Configure the Environment

```bash
cd /opt/dmarc
cp .env.prod.example .env.prod
nano .env.prod
```

### Required values

**1. `SECRET_KEY`** — signs all JWT tokens:
```bash
openssl rand -hex 32
```

**2. `POSTGRES_PASSWORD`** — strong database password:
```bash
openssl rand -hex 24
```
Set the same value in both `POSTGRES_PASSWORD` and the password segment of `DATABASE_URL`.

**3. `ENCRYPTION_KEY`** — encrypts stored IMAP credentials:
```bash
docker run --rm python:3.13-slim python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**4. `ADMIN_EMAIL` and `ADMIN_PASSWORD`** — credentials for the initial super\_admin account.

**5. `CORS_ORIGINS`** — set to your public HTTPS domain:
```
CORS_ORIGINS=https://dmarc.example.com
```

**6. `AZURE_REDIRECT_URI`** (if using Azure SSO):
```
AZURE_REDIRECT_URI=https://dmarc.example.com/auth/callback
```

> **Keep `.env.prod` secure.** It is gitignored and must never be committed. Back up `SECRET_KEY` and `ENCRYPTION_KEY` in a password manager — loss of `ENCRYPTION_KEY` means stored IMAP credentials cannot be decrypted.

---

## GeoIP Database

GeoIP enrichment enables country/city data on DMARC records and powers geo-anomaly detection.

1. Sign up at https://www.maxmind.com/en/geolite2/signup
2. Download **GeoLite2-City.mmdb**
3. Place it on the server:

```bash
# From your local machine:
scp -i ~/.ssh/id_rsa GeoLite2-City.mmdb ubuntu@<public_ip>:/opt/dmarc/geoip/
```

The platform starts normally without the GeoIP database — geo enrichment and geo-anomaly flags are silently disabled.

---

## SSL Certificate with Certbot (Docker)

Certbot runs as a Docker container (`dmarc-prod-certbot`) that shares a volume with the nginx frontend container. This section walks through the one-time bootstrap to obtain the initial certificate.

### How it works

```
certbot container                   nginx (frontend) container
     │                                       │
     │  writes challenge file                │
     ├──────────────────────────────────────▶│ certbot-webroot volume
     │                                       │  /var/www/certbot/.well-known/
     │                                       │
     │  Let's Encrypt reads the file via     │
     │  HTTP from your domain ──────────────▶│ nginx serves it on port 80
     │                                       │
     │  certificate issued ──────────────────▶ certbot-certs volume
     │                                          /etc/letsencrypt/live/DOMAIN/
     │
     │  nginx reads certificate from volume on each reload
```

### Step 1 — Point DNS to the Elastic IP

Create an A record for your domain pointing to the Elastic IP from Terraform output. Wait for DNS propagation before continuing (test with `dig +short your-domain.com`).

### Step 2 — Substitute your domain in the nginx config

```bash
cd /opt/dmarc
sed -i 's/DOMAIN_PLACEHOLDER/dmarc.example.com/g' docker/nginx.prod.conf
```

Verify the substitution:
```bash
grep "ssl_certificate" docker/nginx.prod.conf
# Should show: /etc/letsencrypt/live/dmarc.example.com/fullchain.pem
```

### Step 3 — Authenticate to ECR and pull images

```bash
export ECR_REGISTRY="<registry_url_from_terraform>"
export ECR_API_REPO="dmarc-prod-api"
export ECR_FRONTEND_REPO="dmarc-prod-frontend"
export IMAGE_TAG="latest"

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"
```

> **Note:** Images are not available in ECR until the first GitHub Actions push to `main` completes. Trigger it by pushing a commit (or run the workflow manually in the GitHub Actions UI).

### Step 4 — Start the stack with the bootstrap nginx config

The bootstrap config serves HTTP only — required because the SSL certificate doesn't exist yet.

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.bootstrap.yml up -d
```

Verify the frontend is reachable over HTTP:
```bash
curl -I http://dmarc.example.com
# Should return HTTP 200
```

### Step 5 — Obtain the initial certificate

```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  --domain dmarc.example.com \
  --email your@email.com \
  --agree-tos --no-eff-email
```

Expected output:
```
Saving debug log to /var/log/letsencrypt/letsencrypt.log
Account registered.
Requesting a certificate for dmarc.example.com
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/dmarc.example.com/fullchain.pem
...
```

### Step 6 — Switch to the production HTTPS config

Restart the frontend container — it now mounts `nginx.prod.conf` (from `docker-compose.prod.yml`) and can load the certificate from the shared volume:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate frontend
```

Verify HTTPS:
```bash
curl -I https://dmarc.example.com
# Should return HTTP 200 with TLS details
```

Test the HTTP → HTTPS redirect:
```bash
curl -I http://dmarc.example.com
# Should return HTTP 301 → https://dmarc.example.com
```

---

## First Deployment

If CI/CD is already configured and has built the images, trigger the full stack:

```bash
cd /opt/dmarc
docker compose -f docker-compose.prod.yml up -d
```

Monitor API startup to confirm migrations and seeding complete:

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-api -f --tail 50
```

Expected output sequence:
```
api-1  | ==> Running Alembic migrations...
api-1  | INFO  [alembic.runtime.migration] Running upgrade ...
api-1  | ==> Seeding initial data...
api-1  |   Created super_admin: admin@example.com
api-1  | ==> Starting API server on :8000...
api-1  | INFO:     Application startup complete.
```

Check all containers are healthy:
```bash
docker compose -f docker-compose.prod.yml ps
```

> **ClamAV first boot:** The `dmarc-prod-clamav` container downloads ~300 MB of virus signatures on first start. It shows `starting` until download completes (2–5 minutes). The API and watcher start regardless and operate in fail-closed mode until clamd is ready.

---

## Initial Application Setup via CLI

The seed script creates one super\_admin and (optionally) a test client on first boot. Use the CLI for all subsequent setup.

> **First login — MFA required:** The super\_admin account always requires TOTP MFA. On first login you are redirected to the MFA setup page. Scan the QR code with Microsoft Authenticator, Authy, or Google Authenticator, enter the 6-digit confirmation code, and click **Enable MFA**.

CLI commands run inside the API container:

```bash
docker compose -f docker-compose.prod.yml exec dmarc-prod-api \
  python -m cli.manage <command>
```

### MSP setup example

```bash
EXEC="docker compose -f docker-compose.prod.yml exec dmarc-prod-api python -m cli.manage"

$EXEC create-client acme-corp "Acme Corporation"
$EXEC create-domain acme-corp mail.acme-corp.com
$EXEC create-user stakeholder@acme-corp.com user --client acme-corp --client-role viewer
$EXEC create-user engineer@yourcompany.com user --client acme-corp --client-role admin
```

### Full CLI reference

| Command | Description |
|---------|-------------|
| `create-client <slug> <name>` | Create a client and its incoming report folder |
| `create-domain <slug> <domain>` | Add a domain to a client |
| `create-user <email> <role> [--client <slug>] [--client-role admin\|viewer]` | Create a user |
| `set-role <email> <role>` | Change global role (`super_admin` or `user`) |
| `assign-client <email> <slug> [--role admin\|viewer]` | Add a client assignment |
| `set-client-role <email> <slug> <role>` | Change per-client role |
| `revoke-client <email> <slug>` | Remove a client assignment |
| `reset-password <email> [--temporary]` | Set a new password |
| `list-clients` | List all clients |
| `scan <slug>` | Manually process all files in the client's incoming folder |
| `enrich-geo <slug> [--force]` | Backfill geolocation data |
| `export-client <slug> [--output <path>]` | Export client data to ZIP |
| `purge-client <slug> [--yes]` | Permanently delete all data for a client |

---

## Automated Certificate Renewal

The `dmarc-prod-certbot` container runs `certbot renew` every 12 hours. Certbot automatically renews any certificate with fewer than 30 days remaining.

After renewal, nginx must be reloaded to pick up the new certificate. Add a cron entry to handle this:

```bash
crontab -e
```

Add:
```cron
0 3 * * * docker exec dmarc-prod-frontend nginx -s reload >> /var/log/nginx-reload.log 2>&1
```

This reloads nginx daily at 03:00. Because certbot only renews when expiry is within 30 days, the reload is a no-op 29 days out of 30.

Verify the renewal path manually with a dry run:

```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  renew --webroot -w /var/www/certbot --dry-run
```

Expected output:
```
Simulating renewal of an existing certificate for dmarc.example.com
Congratulations, all simulated renewals succeeded.
```

---

## Automated Backups

### Backup script

Create `/opt/dmarc/backup.sh`:

```bash
nano /opt/dmarc/backup.sh
```

```bash
#!/bin/bash
set -euo pipefail

APP_DIR="/opt/dmarc"
BACKUP_DIR="/opt/dmarc/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

mkdir -p "$BACKUP_DIR"

docker compose -f "$APP_DIR/docker-compose.prod.yml" \
  exec -T dmarc-prod-db pg_dump -U dmarc dmarc \
  | gzip > "$BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"

find "$BACKUP_DIR" -name "dmarc_*.sql.gz" -mtime +"$RETAIN_DAYS" -delete

echo "Backup complete: $BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"
```

```bash
chmod +x /opt/dmarc/backup.sh
```

### Schedule with cron

```bash
crontab -e
```

```cron
0 3 * * * /opt/dmarc/backup.sh >> /var/log/dmarc-backup.log 2>&1
0 3 * * * docker exec dmarc-prod-frontend nginx -s reload >> /var/log/nginx-reload.log 2>&1
```

### Restore procedure

```bash
cd /opt/dmarc

# Stop application containers (keep db running)
docker compose -f docker-compose.prod.yml stop api watcher frontend

# Drop and recreate schema
docker compose -f docker-compose.prod.yml exec -T dmarc-prod-db \
  psql -U dmarc -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Restore from backup
gunzip -c /opt/dmarc/backups/dmarc_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose -f docker-compose.prod.yml exec -T dmarc-prod-db psql -U dmarc dmarc

# Restart
docker compose -f docker-compose.prod.yml up -d
```

---

## Ongoing Operations

### Viewing logs

```bash
# All containers
docker compose -f docker-compose.prod.yml logs -f

# Specific container
docker compose -f docker-compose.prod.yml logs dmarc-prod-api -f --tail 100
docker compose -f docker-compose.prod.yml logs dmarc-prod-watcher -f --tail 100
docker compose -f docker-compose.prod.yml logs dmarc-prod-clamav --tail 50
```

### Container status

```bash
docker compose -f docker-compose.prod.yml ps
```

### Restarting a container

```bash
docker compose -f docker-compose.prod.yml restart dmarc-prod-api
```

### Dropping a DMARC report manually

```bash
# Named Docker volume — find the mount point
docker volume inspect dmarc-prod_app-data

# Copy report to the incoming directory inside the volume
docker cp report.xml.gz dmarc-prod-watcher:/app/data/reports/incoming/acme-corp/
```

### Disk usage

```bash
df -h /
docker system df
docker volume ls
```

---

## Updating the Application

All application updates flow through GitHub Actions:

```bash
git commit -m "your change"
git push origin main
```

GitHub Actions will:
1. Run the test suite
2. Build new images tagged with the commit SHA
3. Push to ECR
4. Use SSM to pull and restart the application containers on EC2

Watch progress in the **Actions** tab of your repository.

### Manual update (if CI/CD is unavailable)

```bash
cd /opt/dmarc

# Set environment from the tag you want to deploy
export ECR_REGISTRY="<registry>"
export ECR_API_REPO="dmarc-prod-api"
export ECR_FRONTEND_REPO="dmarc-prod-frontend"
export IMAGE_TAG="<sha-or-tag>"

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker compose -f docker-compose.prod.yml pull api watcher frontend
docker compose -f docker-compose.prod.yml up -d --no-deps api watcher frontend
```

---

## Troubleshooting

### SSL certificate issues

**nginx fails to start after certbot bootstrap:**
```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-frontend --tail 20
```
Confirm the domain in `docker/nginx.prod.conf` exactly matches the domain in the certificate (`/etc/letsencrypt/live/<domain>/`). Re-run the `sed` substitution if needed.

**Certbot cannot reach the ACME server:**
Verify port 80 is open in the AWS security group and not blocked by ufw (`sudo ufw status`).

**Dry-run renewal fails:**
```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-certbot --tail 30
```
Confirm the `certbot-webroot` volume is mounted in both the certbot and frontend containers.

**Certificate shows old after renewal:**
```bash
docker exec dmarc-prod-frontend nginx -s reload
```
The daily cron handles this automatically, but you can force a reload immediately.

### Container fails to start

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-api --tail 50
```

Common causes:
- Missing or invalid `SECRET_KEY` or `ENCRYPTION_KEY` in `.env.prod`
- `DATABASE_URL` password doesn't match `POSTGRES_PASSWORD`
- ECR image not yet available (first pipeline run hasn't completed)

### 502 Bad Gateway

The API container is not yet healthy. Wait 30 seconds and retry. If persistent:
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs dmarc-prod-api --tail 20
```

### ECR pull fails on EC2

The instance IAM profile should allow ECR read without credentials. Verify:
```bash
aws ecr describe-repositories --region us-east-1
```
If this fails, the instance profile may not be attached. Check the EC2 IAM role in the AWS console.

### ClamAV not accepting connections

On first start, ClamAV downloads ~300 MB of signatures. Allow 5 minutes, then:
```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-clamav --tail 30
```
Expected when ready: `clamd: pid=1: OK`

### SSM deployment not completing

```bash
aws ssm list-command-invocations \
  --instance-id <EC2_INSTANCE_ID> \
  --details --query "CommandInvocations[0]"
```

The SSM agent must be running on the instance:
```bash
sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent
```

### Reports not being processed

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-watcher --tail 50
```

Verify the incoming directory exists inside the app-data volume and the client slug matches exactly:
```bash
docker exec dmarc-prod-watcher ls /app/data/reports/incoming/
```