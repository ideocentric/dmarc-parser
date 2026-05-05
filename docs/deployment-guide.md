# DMARC Intelligence Platform — Deployment Guide

*Ubuntu 24.04 LTS — Docker deployment with CI/CD on AWS, Azure, and Linode*

---

## Table of Contents

1. [Overview](#overview)
2. [Choosing a Deployment Topology](#choosing-a-deployment-topology)
3. [Prerequisites](#prerequisites)
4. [Provision Infrastructure — AWS](#provision-infrastructure--aws)
5. [Provision Infrastructure — Azure](#provision-infrastructure--azure)
6. [Provision Infrastructure — Linode](#provision-infrastructure--linode)
7. [Configure GitHub Actions CI/CD](#configure-github-actions-cicd)
8. [First-Time Server Setup](#first-time-server-setup)
9. [Configure the Environment](#configure-the-environment)
10. [GeoIP Database](#geoip-database)
11. [SSL Certificate with Certbot (Docker)](#ssl-certificate-with-certbot-docker)
12. [First Deployment](#first-deployment)
13. [Initial Application Setup via CLI](#initial-application-setup-via-cli)
14. [Automated Certificate Renewal](#automated-certificate-renewal)
15. [Automated Backups](#automated-backups)
16. [Ongoing Operations](#ongoing-operations)
17. [Updating the Application](#updating-the-application)
18. [Troubleshooting](#troubleshooting)
19. [Appendix A — Estimated Monthly Infrastructure Costs](#appendix-a--estimated-monthly-infrastructure-costs)

---

## Overview

The DMARC Intelligence Platform runs as Docker containers managed by Compose. The frontend container handles TLS directly — no host-level reverse proxy is required. Container images are built by GitHub Actions and pushed to a registry — ECR on AWS, ACR on Azure, or Docker Hub / GitHub Container Registry on Linode — then pulled to the server on each deployment.

Three deployment topologies are supported, controlled by a single Terraform variable. See [Choosing a Deployment Topology](#choosing-a-deployment-topology) before provisioning.

### Standalone topology

All services — including PostgreSQL — run on a single VM.

```mermaid
flowchart TD
    Internet(["Internet\nHTTPS :443 / HTTP :80"])

    subgraph vm["App VM — public subnet"]
        subgraph docker["Docker network — dmarc-prod"]
            FE["frontend\nnginx :80 / :443"]
            API["api\nuvicorn :8000"]
            DB[("db\nPostgreSQL :5432")]
            W["watcher\n+ scheduler"]
            CB["certbot\nrenewal loop"]
            AV["clamav\nclamd :3310"]
        end
    end

    Internet --> FE
    FE -->|"/api/*"| API
    API <--> DB
    W <--> DB
    W -. scan .-> AV
    API -. scan .-> AV
```

### split_vm topology

The application runs on a public VM; PostgreSQL runs on a separate VM in a private subnet with no internet exposure.

```mermaid
flowchart TD
    Internet(["Internet\nHTTPS :443 / HTTP :80"])

    subgraph public["App VM — public subnet"]
        subgraph docker["Docker network — dmarc-prod"]
            FE["frontend\nnginx :80/:443"]
            API["api\nuvicorn :8000"]
            W["watcher\n+ scheduler"]
            CB["certbot\nrenewal loop"]
            AV["clamav\nclamd :3310"]
        end
    end

    subgraph private["DB VM — private subnet  ·  no public IP"]
        DB[("PostgreSQL\n:5432")]
        NAT["NAT Gateway\n(outbound only)"]
    end

    Internet --> FE
    FE -->|"/api/*"| API
    API <-->|":5432"| DB
    W <-->|":5432"| DB
    W -. scan .-> AV
    API -. scan .-> AV
    DB -.->|OS updates| NAT
```

### split_managed topology

The application runs on a public VM; PostgreSQL is a fully managed cloud service in a private network.

```mermaid
flowchart TD
    Internet(["Internet\nHTTPS :443 / HTTP :80"])

    subgraph public["App VM — public subnet"]
        subgraph docker["Docker network — dmarc-prod"]
            FE["frontend\nnginx :80/:443"]
            API["api\nuvicorn :8000"]
            W["watcher\n+ scheduler"]
            CB["certbot\nrenewal loop"]
            AV["clamav\nclamd :3310"]
        end
    end

    subgraph private["Managed PostgreSQL — private network"]
        DB[("AWS RDS\nor Azure PostgreSQL\nor Linode Managed PG")]
        BK["Automated backups\nNo OS management"]
    end

    Internet --> FE
    FE -->|"/api/*"| API
    API <-->|":5432"| DB
    W <-->|":5432"| DB
    W -. scan .-> AV
    API -. scan .-> AV
```

---

## Choosing a Deployment Topology

| | `standalone` | `split_vm` | `split_managed` |
|---|---|---|---|
| **Best for** | Development, small deployments | Separation without managed cost | Production, compliance |
| **Database management** | Self (Docker) | Self (PostgreSQL on EC2/VM) | Cloud provider |
| **Automated backups** | Manual script | Manual script | Built-in, configurable retention |
| **Failover** | None | None | Multi-AZ option (RDS) |
| **Cost** | Lowest | Low (extra VM) | Higher (managed service fee) |
| **Operational complexity** | Lowest | Medium | Lowest for DB ops |
| **Extra infrastructure** | None | Private subnet + NAT Gateway | Private subnet + NAT Gateway + managed service |

**Recommendation:** Start with `standalone` to verify the deployment, then migrate to `split_managed` for production. The database host is the only change in `.env.prod` when switching — application code and containers are identical across all three modes.

> **NAT Gateway cost note:** On AWS and Azure, `split_vm` and `split_managed` both create a NAT Gateway to give the private subnet outbound internet access (OS updates, registry pulls from the DB VM). On AWS this is ~$0.045/hr (~$33/month) plus data transfer; on Azure ~$0.045/hr. On Linode, VPC interfaces are additive — the DB Linode retains its own public IP for outbound traffic, so no NAT Gateway is needed or created.

---

## Prerequisites

### All providers

- [ ] Terraform ≥ 1.5 installed locally
- [ ] An SSH key pair on your local machine (`~/.ssh/id_rsa` and `~/.ssh/id_rsa.pub`)
- [ ] A registered domain name (DNS A record will point to the server's static IP)
- [ ] A GitHub repository containing the application code
- [ ] (Optional) A free MaxMind account for GeoIP data

### AWS

- [ ] AWS CLI configured with credentials that can create VPCs, EC2, ECR, IAM, and RDS resources
- [ ] Permissions to create IAM roles and attach managed policies

### Azure

- [ ] Azure CLI installed and authenticated (`az login`)
- [ ] A subscription with Contributor access (needed for role assignments)
- [ ] `az account show` confirms the correct subscription is active

### Linode

- [ ] A Linode account with a Personal Access Token (create at **cloud.linode.com → Profile → API Tokens**)
- [ ] Token scopes: Linodes, Firewalls, VPCs, Databases, IPs — all Read/Write
- [ ] A container registry account: Docker Hub (`docker.io`) or GitHub Container Registry (`ghcr.io`) — Linode has no native registry

### Server sizing

| | Without ClamAV | With ClamAV (default) |
|---|---|---|
| **AWS** | t3.medium (2 vCPU / 4 GB) | **t3.large (2 vCPU / 8 GB)** |
| **Azure** | Standard_B2s (2 vCPU / 4 GB) | **Standard_B2ms (2 vCPU / 8 GB)** |
| **Linode** | g6-standard-2 (2 vCPU / 4 GB) | **g6-standard-4 (4 vCPU / 8 GB)** |
| **Disk** | 50 GB | **100 GB** |

ClamAV loads 700 MB–1 GB of virus signatures into RAM at startup. The Terraform configuration auto-selects the larger VM size when `clamav_enabled = true`.

---

## Provision Infrastructure — AWS

The Terraform configuration in `terraform/aws/` provisions all infrastructure using the naming convention `{project}-{environment}-{resource}` (e.g. `dmarc-prod-vpc`).

### Resources created — all topologies

| Resource | Name |
|---|---|
| VPC | `dmarc-prod-vpc` |
| Internet Gateway | `dmarc-prod-igw` |
| Public Subnet | `dmarc-prod-public-subnet` |
| App Security Group | `dmarc-prod-app-sg` |
| EC2 Instance | `dmarc-prod-app-ec2` |
| Elastic IP | `dmarc-prod-eip` |
| Key Pair | `dmarc-prod-keypair` |
| ECR Repositories | `dmarc-prod-api`, `dmarc-prod-frontend` |
| IAM Role + Profile | `dmarc-prod-ec2-role`, `dmarc-prod-ec2-profile` |

### Additional resources — split topologies

| Resource | split_vm | split_managed |
|---|---|---|
| Private Subnet (×2, multi-AZ) | ✓ | ✓ |
| NAT Gateway + EIP | ✓ | ✓ |
| DB Security Group | ✓ | ✓ |
| DB EC2 Instance (`dmarc-prod-db-ec2`) | ✓ | — |
| RDS Instance (`dmarc-prod-rds`) | — | ✓ |
| RDS Subnet Group | — | ✓ |

### Security group rules

| Group | Port | Source | Purpose |
|---|---|---|---|
| `dmarc-prod-app-sg` | 443 | `0.0.0.0/0` | HTTPS |
| `dmarc-prod-app-sg` | 80 | `0.0.0.0/0` | HTTP (ACME + redirect) |
| `dmarc-prod-app-sg` | 22 | `admin_cidr` | SSH — your IP only |
| `dmarc-prod-app-sg` | 22 | `cicd_cidr` | SSH — CI/CD (optional) |
| `dmarc-prod-db-sg` | 5432 | app security group | PostgreSQL from app only |

### Deploy

```bash
cd terraform/aws
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`. Required values:

```hcl
# Your public IP — find it: curl -s https://checkip.amazonaws.com
admin_cidr = "203.0.113.5/32"

ssh_public_key_path = "~/.ssh/id_rsa.pub"

# For split_vm or split_managed:
# deployment_mode = "split_vm"
# db_password     = "$(openssl rand -hex 24)"
```

Then:

```bash
terraform init
terraform plan
terraform apply
```

### Key outputs

```bash
terraform output public_ip          # Point your DNS A record here
terraform output instance_id        # → GitHub secret EC2_INSTANCE_ID
terraform output ecr_registry_url   # → GitHub secret ECR_REGISTRY
terraform output ecr_api_repo       # → GitHub secret ECR_API_REPO
terraform output ecr_frontend_repo  # → GitHub secret ECR_FRONTEND_REPO

# Split topologies only:
terraform output -raw database_url  # → paste into .env.prod on the server
```

### CI/CD IAM credentials (AWS)

The EC2 instance IAM profile allows ECR pulls without stored credentials. For the GitHub Actions *build and push* step, a separate identity with ECR push access is required.

**Option A — Dedicated IAM user**

Set `create_ci_user = true` in `terraform.tfvars` and re-apply:

```bash
terraform apply
terraform output ci_user_access_key_id
terraform output -raw ci_user_secret_access_key
```

Store as GitHub secrets `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

**Option B — GitHub Actions OIDC (recommended)**

No long-lived credentials. See:
https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services

Update `.github/workflows/deploy.yml` to use `role-to-assume`.

---

## Provision Infrastructure — Azure

The Terraform configuration in `terraform/azure/` provisions all infrastructure in a single Resource Group using the same naming convention `{project}-{environment}-{resource}`.

### Resources created — all topologies

| Resource | Name |
|---|---|
| Resource Group | `dmarc-prod-rg` |
| Virtual Network | `dmarc-prod-vnet` |
| Public Subnet + NSG | `dmarc-prod-public-snet`, `dmarc-prod-app-nsg` |
| Static Public IP | `dmarc-prod-pip` |
| NIC + VM | `dmarc-prod-nic`, `dmarc-prod-vm` |
| Container Registry | `dmarcprodacr` |
| Managed Identity | `dmarc-prod-mi` (AcrPull role assigned) |

### Additional resources — split topologies

| Resource | split_vm | split_managed |
|---|---|---|
| Private Subnet + NSG | ✓ | ✓ |
| NAT Gateway | ✓ | ✓ |
| DB VM (`dmarc-prod-db-vm`) | ✓ | — |
| Delegated Subnet (`dmarc-prod-db-snet`) | — | ✓ |
| PostgreSQL Flexible Server (`dmarc-prod-pgsql`) | — | ✓ |
| Private DNS Zone | — | ✓ |

> **ACR name uniqueness:** Azure Container Registry names are globally unique and alphanumeric only. Terraform computes the name as `${project}${environment}acr` → `dmarcprodacr`. If this name is already taken, adjust `project_name` or `environment` in `terraform.tfvars`.

> **Delegated subnet:** Azure PostgreSQL Flexible Server requires an exclusively delegated subnet — no other resources can use it. `split_managed` creates a separate `db-snet` (`10.0.3.0/24`) for this purpose alongside the private subnet (`10.0.2.0/24`) used by the DB VM in `split_vm`.

### NSG rules

| NSG | Port | Source | Purpose |
|---|---|---|---|
| `dmarc-prod-app-nsg` | 443 | `*` | HTTPS |
| `dmarc-prod-app-nsg` | 80 | `*` | HTTP (ACME + redirect) |
| `dmarc-prod-app-nsg` | 22 | `admin_cidr` | SSH — your IP only |
| `dmarc-prod-app-nsg` | 22 | `cicd_cidr` | SSH — CI/CD (optional) |
| `dmarc-prod-db-nsg` | 5432 | VNet address space | PostgreSQL from VNet only |

### Deploy

```bash
cd terraform/azure
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`. Required values:

```hcl
# az account show --query id -o tsv
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

location   = "East US"
admin_cidr = "203.0.113.5/32"

ssh_public_key_path = "~/.ssh/id_rsa.pub"

# For split_vm or split_managed:
# deployment_mode = "split_managed"
# db_password     = "$(openssl rand -hex 24)"
```

Then:

```bash
az login
terraform init
terraform plan
terraform apply
```

### Key outputs

```bash
terraform output public_ip            # Point your DNS A record here
terraform output vm_name              # → GitHub secret AZURE_VM_NAME
terraform output resource_group_name  # → GitHub secret AZURE_RESOURCE_GROUP
terraform output acr_login_server     # → GitHub secret ACR_LOGIN_SERVER

# Split topologies only:
terraform output -raw database_url    # → paste into .env.prod on the server
```

### CI/CD service principal (Azure)

GitHub Actions needs a service principal with ACR push and VM Run Command permissions.

```bash
# Create a service principal scoped to the resource group
az ad sp create-for-rbac \
  --name "dmarc-prod-github-actions" \
  --role Contributor \
  --scopes /subscriptions/<subscription_id>/resourceGroups/dmarc-prod-rg \
  --sdk-auth
```

Store the output JSON fields as GitHub secrets:

| Secret | JSON field |
|---|---|
| `AZURE_CLIENT_ID` | `clientId` |
| `AZURE_CLIENT_SECRET` | `clientSecret` |
| `AZURE_TENANT_ID` | `tenantId` |
| `AZURE_SUBSCRIPTION_ID` | `subscriptionId` |

**GitHub Actions OIDC (recommended):** See
https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-azure

---

## Provision Infrastructure — Linode

The Terraform configuration in `terraform/linode/` provisions all infrastructure using the same naming convention `{project}-{environment}-{resource}`. Linode has no native container registry — images must be hosted on Docker Hub or GitHub Container Registry.

### Resources created — all topologies

| Resource | Name |
|---|---|
| Linode Instance | `dmarc-prod-app` |
| App Firewall | `dmarc-prod-app-fw` |
| Bootstrap StackScript | `dmarc-prod-docker-bootstrap` |

### Additional resources — split topologies

| Resource | split_vm | split_managed |
|---|---|---|
| VPC | ✓ | ✓ |
| VPC Subnet (`10.8.0.0/24`) | ✓ | ✓ |
| DB Firewall | ✓ | ✓ |
| DB Linode Instance (`dmarc-prod-db`) | ✓ | — |
| Linode Managed PostgreSQL (`dmarc-prod-db`) | — | ✓ |

> **No NAT Gateway:** Linode VPC interfaces are additive. The DB Linode retains its public IP for outbound internet access; only PostgreSQL port 5432 is isolated to the VPC CIDR by the DB firewall.

### Firewall rules

| Firewall | Port | Source | Purpose |
|---|---|---|---|
| `dmarc-prod-app-fw` | 443 | `0.0.0.0/0` | HTTPS |
| `dmarc-prod-app-fw` | 80 | `0.0.0.0/0` | HTTP (ACME + redirect) |
| `dmarc-prod-app-fw` | 22 | `admin_cidr` | SSH — your IP only |
| `dmarc-prod-db-fw` | 22 | `admin_cidr` | SSH admin access to DB Linode |
| `dmarc-prod-db-fw` | 5432 | `vpc_subnet_cidr` | PostgreSQL — VPC only |

### Deploy

```bash
cd terraform/linode
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`. Required values:

```hcl
# Linode API personal access token
linode_token = "your-linode-api-token"

# Your public IP — find it: curl -s https://checkip.amazonaws.com
admin_cidr = "203.0.113.5/32"

ssh_public_key_path = "~/.ssh/id_rsa.pub"

# For split_vm or split_managed:
# deployment_mode = "split_vm"
# db_password     = "$(openssl rand -hex 24)"    # split_vm only
```

Then:

```bash
terraform init
terraform plan
terraform apply
```

### Key outputs

```bash
terraform output public_ip      # Point your DNS A record here
terraform output ssh_command    # SSH command to connect to the server

# Split topologies only:
terraform output -raw database_url   # paste into .env.prod
terraform output -raw db_password    # auto-generated for split_managed
```

### CI/CD for Linode

Linode has no SSM or VM Run Command equivalent — deployment uses SSH. Store the following as GitHub Actions secrets:

| Secret | Value |
|---|---|
| `LINODE_HOST` | `terraform output -raw public_ip` |
| `SSH_PRIVATE_KEY` | Contents of `~/.ssh/id_rsa` (your private key) |
| `REGISTRY_USERNAME` | Docker Hub username or GitHub username |
| `REGISTRY_PASSWORD` | Docker Hub access token or GitHub PAT |
| `REGISTRY_IMAGE_API` | e.g. `docker.io/yourorg/dmarc-api` or `ghcr.io/yourorg/dmarc-api` |
| `REGISTRY_IMAGE_FRONTEND` | e.g. `docker.io/yourorg/dmarc-frontend` |

A minimal deploy step in `.github/workflows/deploy-linode.yml`:

```yaml
- name: Deploy to Linode
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.LINODE_HOST }}
    username: root
    key: ${{ secrets.SSH_PRIVATE_KEY }}
    script: |
      cd /opt/dmarc
      echo "${{ secrets.REGISTRY_PASSWORD }}" \
        | docker login docker.io -u "${{ secrets.REGISTRY_USERNAME }}" --password-stdin
      IMAGE_TAG=${{ github.sha }}
      export REGISTRY_IMAGE_API=${{ secrets.REGISTRY_IMAGE_API }}
      export REGISTRY_IMAGE_FRONTEND=${{ secrets.REGISTRY_IMAGE_FRONTEND }}
      docker compose -f docker-compose.prod.yml pull api watcher frontend
      docker compose -f docker-compose.prod.yml up -d --no-deps api watcher frontend
```

Update `docker-compose.prod.yml` image references to use your registry path (e.g. `docker.io/yourorg/dmarc-api:${IMAGE_TAG}`).

---

## Configure GitHub Actions CI/CD

### AWS secrets

In your GitHub repository: **Settings → Secrets and variables → Actions**

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | CI IAM user key or OIDC |
| `AWS_SECRET_ACCESS_KEY` | CI IAM user secret or OIDC |
| `ECR_REGISTRY` | `terraform output ecr_registry_url` |
| `ECR_API_REPO` | `terraform output ecr_api_repo` |
| `ECR_FRONTEND_REPO` | `terraform output ecr_frontend_repo` |
| `EC2_INSTANCE_ID` | `terraform output instance_id` |

### Azure secrets

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | Service principal client ID |
| `AZURE_CLIENT_SECRET` | Service principal secret |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `ACR_LOGIN_SERVER` | `terraform output acr_login_server` |
| `AZURE_RESOURCE_GROUP` | `terraform output resource_group_name` |
| `AZURE_VM_NAME` | `terraform output vm_name` |

### How deployment works

**AWS** (`.github/workflows/deploy.yml`):
1. **Test** — runs pytest inside the API image
2. **Build & Push** — builds API and frontend images tagged with the 8-char git SHA, pushes to ECR
3. **Deploy** — uses `aws ssm send-command` to pull and restart containers on EC2 (no SSH port needs to be open to GitHub runner IPs)

**Azure** (`.github/workflows/deploy-azure.yml`):
1. **Test** — same pytest run
2. **Build & Push** — builds and pushes to ACR
3. **Deploy** — uses `az vm run-command invoke` to pull and restart containers (equivalent to SSM)

---

## First-Time Server Setup

SSH into the application server:

```bash
# AWS
ssh -i ~/.ssh/id_rsa ubuntu@$(terraform -chdir=terraform/aws output -raw public_ip)

# Azure
ssh -i ~/.ssh/id_rsa ubuntu@$(terraform -chdir=terraform/azure output -raw public_ip)

# Linode (root user — no ubuntu user on Linode images)
ssh -i ~/.ssh/id_rsa root@$(terraform -chdir=terraform/linode output -raw public_ip)
```

Docker was installed by the cloud-init script during provisioning. Verify:

```bash
docker --version
docker compose version
```

Copy the deployment files from your local machine:

```bash
PUBLIC_IP="<your-server-ip>"

scp -i ~/.ssh/id_rsa \
  docker-compose.prod.yml \
  docker-compose.bootstrap.yml \
  .env.prod.example \
  ubuntu@$PUBLIC_IP:/opt/dmarc/

scp -i ~/.ssh/id_rsa \
  docker/nginx.prod.conf \
  docker/nginx.bootstrap.conf \
  ubuntu@$PUBLIC_IP:/opt/dmarc/docker/
```

Or clone the full repository on the server:

```bash
git clone <repository-url> /opt/dmarc
cd /opt/dmarc
```

### split_vm: accessing the DB VM

**AWS / Azure** — the DB VM has no public IP; reach it through the app VM as a jump host:

```bash
# AWS — connect to DB EC2 via app EC2
ssh -i ~/.ssh/id_rsa -J ubuntu@<app_public_ip> ubuntu@<db_private_ip>

# Azure — connect to DB VM via app VM
ssh -i ~/.ssh/id_rsa -J ubuntu@<app_public_ip> ubuntu@<db_private_ip>
```

**Linode** — the DB Linode retains its own public IP (SSH firewalled to `admin_cidr` only):

```bash
# Linode — SSH directly to the DB Linode
ssh -i ~/.ssh/id_rsa root@<db_public_ip>
```

The DB host (VPC IP for app connectivity) is available from Terraform: `terraform output db_host`

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

For **standalone**: set the same value in both `POSTGRES_PASSWORD` and the password segment of `DATABASE_URL`.

For **split topologies**: `DATABASE_URL` points to the external database host. Use the value from Terraform:
```bash
terraform output -raw database_url
# postgresql+psycopg2://dmarc:password@10.0.2.x:5432/dmarc   (split_vm)
# postgresql+psycopg2://dmarc:password@dmarc-prod-rds.xxxx.rds.amazonaws.com:5432/dmarc  (AWS split_managed)
# postgresql+psycopg2://dmarc_admin:password@dmarc-prod-pgsql.postgres.database.azure.com:5432/dmarc  (Azure split_managed)
```

**3. `ENCRYPTION_KEY`** — encrypts stored IMAP credentials:
```bash
docker run --rm python:3.13-slim python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**4. `ADMIN_EMAIL` and `ADMIN_PASSWORD`** — credentials for the initial super_admin account.

**5. `CORS_ORIGINS`** — set to your public HTTPS domain:
```
CORS_ORIGINS=https://dmarc.example.com
```

**6. ClamAV** — confirm these match the `docker-compose.prod.yml` service name:
```
CLAMAV_ENABLED=true
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
```

### split topologies: disable the local DB container

`docker-compose.prod.yml` includes a local PostgreSQL `db` service for standalone deployments. In split topologies this service is unused — the application connects to the external database via `DATABASE_URL`. Comment out the `db` service to avoid running an unnecessary container:

```bash
# In docker-compose.prod.yml, comment out the entire db: service block
# and its reference in api/watcher depends_on:
nano /opt/dmarc/docker-compose.prod.yml
```

Mark `db:` and its blocks with `#`. Also remove or comment the `db:` entry from the `depends_on:` sections of `api` and `watcher` — otherwise those services will wait indefinitely for a container that isn't starting.

> **Keep `.env.prod` secure.** It is gitignored and must never be committed. Back up `SECRET_KEY` and `ENCRYPTION_KEY` in a password manager — loss of `ENCRYPTION_KEY` means stored IMAP credentials cannot be decrypted.

---

## GeoIP Database

GeoIP enrichment enables country/city data on DMARC records and powers geo-anomaly detection.

1. Sign up at https://www.maxmind.com/en/geolite2/signup
2. Download **GeoLite2-City.mmdb**
3. Place it on the server:

```bash
scp -i ~/.ssh/id_rsa GeoLite2-City.mmdb ubuntu@<public_ip>:/opt/dmarc/geoip/
```

The platform starts normally without the GeoIP database — geo enrichment and geo-anomaly flags are silently disabled.

---

## SSL Certificate with Certbot (Docker)

Certbot runs as a Docker container (`dmarc-prod-certbot`) sharing volumes with the nginx frontend. This one-time bootstrap solves the chicken-and-egg problem: nginx needs a certificate to serve HTTPS, but certbot needs nginx running on port 80 to prove domain ownership.

### How it works

```mermaid
sequenceDiagram
    participant C as certbot container
    participant N as nginx (frontend)
    participant LE as Let's Encrypt ACME

    C->>N: write challenge file to<br/>shared certbot-webroot volume
    LE->>N: HTTP GET /.well-known/acme-challenge/
    N-->>LE: serve challenge file
    LE-->>C: domain ownership confirmed
    LE-->>C: certificate issued
    C->>N: store cert in<br/>shared certbot-certs volume
    N->>N: reload — serve HTTPS<br/>with new certificate
```

### Step 1 — Point DNS to the static IP

Create an A record for your domain pointing to the Elastic IP (AWS) or static public IP (Azure). Verify propagation:

```bash
dig +short dmarc.example.com
# Should return the IP from terraform output public_ip
```

### Step 2 — Substitute your domain in the nginx config

```bash
cd /opt/dmarc
sed -i 's/DOMAIN_PLACEHOLDER/dmarc.example.com/g' docker/nginx.prod.conf

# Verify
grep "ssl_certificate" docker/nginx.prod.conf
# Expected: /etc/letsencrypt/live/dmarc.example.com/fullchain.pem
```

### Step 3 — Authenticate to the container registry and pull images

**AWS:**
```bash
export ECR_REGISTRY="$(terraform -chdir=terraform/aws output -raw ecr_registry_url)"
export ECR_API_REPO="dmarc-prod-api"
export ECR_FRONTEND_REPO="dmarc-prod-frontend"
export IMAGE_TAG="latest"

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"
```

**Azure:**
```bash
export ECR_REGISTRY="$(terraform -chdir=terraform/azure output -raw acr_login_server)"
export ECR_API_REPO="dmarc-prod-api"
export ECR_FRONTEND_REPO="dmarc-prod-frontend"
export IMAGE_TAG="latest"

az login --identity
az acr login --name "$ECR_REGISTRY"
```

**Linode (Docker Hub or GitHub Container Registry):**
```bash
# Docker Hub
export ECR_REGISTRY="docker.io"
export ECR_API_REPO="yourorg/dmarc-api"
export ECR_FRONTEND_REPO="yourorg/dmarc-frontend"
export IMAGE_TAG="latest"

echo "<your-docker-hub-token>" | docker login docker.io -u "<your-username>" --password-stdin

# GitHub Container Registry
export ECR_REGISTRY="ghcr.io"
export ECR_API_REPO="yourorg/dmarc-api"
export ECR_FRONTEND_REPO="yourorg/dmarc-frontend"

echo "<your-github-pat>" | docker login ghcr.io -u "<your-github-username>" --password-stdin
```

> Images are not available until the first GitHub Actions push to `main` completes. Trigger it via the Actions UI or by pushing a commit.

### Step 4 — Start with the bootstrap nginx config

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.bootstrap.yml up -d

# Verify HTTP is reachable
curl -I http://dmarc.example.com
# Expected: HTTP/1.1 200 OK
```

### Step 5 — Obtain the initial certificate

```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  --domain dmarc.example.com \
  --email your@email.com \
  --agree-tos --no-eff-email
```

Expected:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/dmarc.example.com/fullchain.pem
```

### Step 6 — Switch to the production HTTPS config

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate frontend

# Verify HTTPS
curl -I https://dmarc.example.com
# Expected: HTTP/2 200

# Verify redirect
curl -I http://dmarc.example.com
# Expected: HTTP/1.1 301 → https://dmarc.example.com
```

---

## First Deployment

Start the full stack:

```bash
cd /opt/dmarc
docker compose -f docker-compose.prod.yml up -d
```

Monitor API startup:

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-api -f --tail 50
```

Expected:
```
api-1  | ==> Running Alembic migrations...
api-1  | ==> Seeding initial data...
api-1  |   Created super_admin: admin@example.com
api-1  | ==> Starting API server on :8000...
api-1  | INFO:     Application startup complete.
```

Check all containers are healthy:

```bash
docker compose -f docker-compose.prod.yml ps
```

> **ClamAV first boot:** `dmarc-prod-clamav` downloads ~300 MB of virus signatures on first start and shows `starting` for 2–5 minutes. The API and watcher start regardless and operate in fail-closed mode until clamd is ready.

> **split_managed first boot:** The managed PostgreSQL service (RDS or Azure Flexible Server) may take 5–10 minutes to become available after `terraform apply`. The API container will retry the connection — monitor with `docker compose logs dmarc-prod-api -f`.

---

## Initial Application Setup via CLI

The seed script creates one super_admin on first boot. Use the CLI for all subsequent setup.

> **First login — MFA required:** The super_admin account always requires TOTP MFA. On first login you are redirected to the MFA setup page. Scan the QR code with Microsoft Authenticator, Authy, or Google Authenticator, enter the 6-digit confirmation code, and click **Enable MFA**.

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
| `scan <slug>` | Manually process files in the client's incoming folder |
| `enrich-geo <slug> [--force]` | Backfill geolocation data |
| `export-client <slug> [--output <path>]` | Export client data to ZIP |
| `purge-client <slug> [--yes]` | Permanently delete all data for a client |

---

## Automated Certificate Renewal

The `dmarc-prod-certbot` container checks for renewal every 12 hours and renews any certificate with fewer than 30 days remaining. After renewal, nginx must reload to load the new certificate. Add a daily cron entry:

```bash
crontab -e
```

```cron
0 3 * * * docker exec dmarc-prod-frontend nginx -s reload >> /var/log/nginx-reload.log 2>&1
```

Verify the renewal path:

```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  renew --webroot -w /var/www/certbot --dry-run
```

Expected: `Congratulations, all simulated renewals succeeded.`

---

## Automated Backups

The backup procedure varies by topology. Choose the section that matches your deployment.

### standalone — database in Docker

The PostgreSQL container manages the data. Back it up with `pg_dump` via `docker exec`:

**Create `/opt/dmarc/backup.sh`:**

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/dmarc/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

mkdir -p "$BACKUP_DIR"

docker compose -f /opt/dmarc/docker-compose.prod.yml \
  exec -T dmarc-prod-db pg_dump -U dmarc dmarc \
  | gzip > "$BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"

find "$BACKUP_DIR" -name "dmarc_*.sql.gz" -mtime +"$RETAIN_DAYS" -delete
echo "Backup complete: $BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"
```

**Restore:**

```bash
cd /opt/dmarc
docker compose -f docker-compose.prod.yml stop api watcher frontend
docker compose -f docker-compose.prod.yml exec -T dmarc-prod-db \
  psql -U dmarc -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
gunzip -c /opt/dmarc/backups/dmarc_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose -f docker-compose.prod.yml exec -T dmarc-prod-db psql -U dmarc dmarc
docker compose -f docker-compose.prod.yml up -d
```

---

### split_vm — database on a private VM

Connect to the DB VM through the app VM as a jump host and run `pg_dump` directly.

**Create `/opt/dmarc/backup.sh` on the app VM:**

```bash
#!/bin/bash
set -euo pipefail

DB_HOST="$(grep DATABASE_URL /opt/dmarc/.env.prod | grep -oP '(?<=@)[^:]+(?=:5432)')"
DB_USER="dmarc"
DB_NAME="dmarc"
BACKUP_DIR="/opt/dmarc/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=30

mkdir -p "$BACKUP_DIR"

PGPASSWORD="$(grep DATABASE_URL /opt/dmarc/.env.prod | grep -oP '(?<=:)[^@]+(?=@)')" \
  pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" \
  | gzip > "$BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"

find "$BACKUP_DIR" -name "dmarc_*.sql.gz" -mtime +"$RETAIN_DAYS" -delete
echo "Backup complete: $BACKUP_DIR/dmarc_${TIMESTAMP}.sql.gz"
```

Install the PostgreSQL client tools on the app VM if not already present:

```bash
sudo apt-get install -y postgresql-client
```

**Restore:**

```bash
DB_HOST="<db_private_ip>"
PGPASSWORD="<db_password>" \
  psql -h "$DB_HOST" -U dmarc -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
PGPASSWORD="<db_password>" \
  gunzip -c /opt/dmarc/backups/dmarc_YYYYMMDD_HHMMSS.sql.gz \
  | psql -h "$DB_HOST" -U dmarc dmarc
```

---

### split_managed — managed PostgreSQL

Automated backups are configured by Terraform (`db_backup_retention_days`, default 7 days). Manual snapshots and point-in-time recovery are available through the cloud console.

**AWS RDS:**

```bash
# Manual snapshot via CLI
aws rds create-db-snapshot \
  --db-instance-identifier dmarc-prod-rds \
  --db-snapshot-identifier dmarc-prod-manual-$(date +%Y%m%d)

# List available snapshots
aws rds describe-db-snapshots \
  --db-instance-identifier dmarc-prod-rds \
  --query "DBSnapshots[*].[DBSnapshotIdentifier,SnapshotCreateTime,Status]" \
  --output table
```

**Azure PostgreSQL Flexible Server:**

```bash
# Backups are automatic — view them in the portal or via CLI
az postgres flexible-server backup list \
  --resource-group dmarc-prod-rg \
  --name dmarc-prod-pgsql \
  --output table
```

**Off-site export (both clouds):**

For a portable `pg_dump` backup from the app VM (connects to the managed endpoint):

```bash
PGPASSWORD="<db_password>" pg_dump \
  -h <rds_or_pgsql_endpoint> \
  -U dmarc_admin dmarc \
  | gzip > /opt/dmarc/backups/dmarc_$(date +%Y%m%d_%H%M%S).sql.gz
```

---

### Schedule backups with cron (standalone and split_vm)

```bash
chmod +x /opt/dmarc/backup.sh
crontab -e
```

```cron
# Daily backup at 02:00
0 2 * * * /opt/dmarc/backup.sh >> /var/log/dmarc-backup.log 2>&1

# Daily nginx reload for certificate pickup at 03:00
0 3 * * * docker exec dmarc-prod-frontend nginx -s reload >> /var/log/nginx-reload.log 2>&1
```

> **Off-site backup:** Copy backup files to a remote location using `rclone` or `aws s3 cp`. A local-only backup does not protect against server loss.

---

## Ongoing Operations

### Viewing logs

```bash
docker compose -f docker-compose.prod.yml logs -f
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

All application updates flow through GitHub Actions on push to `main`:

1. Runs the test suite
2. Builds new images tagged with the commit SHA
3. Pushes to ECR (AWS), ACR (Azure), or Docker Hub / GHCR (Linode)
4. Deploys via SSM (AWS), VM Run Command (Azure), or SSH (Linode)

### Manual update

**AWS:**

```bash
cd /opt/dmarc
export ECR_REGISTRY="<registry>"
export ECR_API_REPO="dmarc-prod-api"
export ECR_FRONTEND_REPO="dmarc-prod-frontend"
export IMAGE_TAG="<sha-or-tag>"

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker compose -f docker-compose.prod.yml pull api watcher frontend
docker compose -f docker-compose.prod.yml up -d --no-deps api watcher frontend
```

**Azure:**

```bash
cd /opt/dmarc
export ECR_REGISTRY="<acr_login_server>"
export ECR_API_REPO="dmarc-prod-api"
export ECR_FRONTEND_REPO="dmarc-prod-frontend"
export IMAGE_TAG="<sha-or-tag>"

az login --identity
az acr login --name "$ECR_REGISTRY"

docker compose -f docker-compose.prod.yml pull api watcher frontend
docker compose -f docker-compose.prod.yml up -d --no-deps api watcher frontend
```

**Linode:**

```bash
cd /opt/dmarc
export ECR_REGISTRY="docker.io"   # or ghcr.io
export ECR_API_REPO="yourorg/dmarc-api"
export ECR_FRONTEND_REPO="yourorg/dmarc-frontend"
export IMAGE_TAG="<sha-or-tag>"

echo "<registry-token>" | docker login "$ECR_REGISTRY" -u "<username>" --password-stdin

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
Confirm the domain in `docker/nginx.prod.conf` exactly matches the certificate path. Re-run the `sed` substitution if needed.

**Certbot cannot reach the ACME server:**
Verify port 80 is open in the security group (AWS) or NSG (Azure). Confirm DNS has propagated: `dig +short your-domain.com`

**Certificate shows old after renewal:**
```bash
docker exec dmarc-prod-frontend nginx -s reload
```

---

### Database connectivity (split topologies)

**API fails to connect to the database:**

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-api --tail 30
# Look for: sqlalchemy.exc.OperationalError: could not connect to server
```

1. Confirm `DATABASE_URL` in `.env.prod` uses the correct host (private IP for `split_vm`, FQDN for `split_managed`).
2. Verify the database host is reachable from the app VM:
   ```bash
   # From the app VM:
   nc -zv <db_host> 5432
   # Expected: Connection succeeded
   ```
3. Check security group / NSG rules allow port 5432 from the app VM's private IP to the DB.

**split_vm — PostgreSQL not listening:**

SSH to the DB VM (via jump host) and check PostgreSQL status:
```bash
sudo systemctl status postgresql
sudo -u postgres psql -c "\l"  # list databases
```

If the user or database is missing, cloud-init may have failed. Check the log:
```bash
sudo cat /var/log/cloud-init-output.log | tail -50
```

**split_managed (AWS RDS) — endpoint not resolving:**

RDS endpoint hostnames resolve only within the VPC. Verify the EC2 instance is in the same VPC:
```bash
nslookup dmarc-prod-rds.xxxx.us-east-1.rds.amazonaws.com
```
If the lookup fails, check that `enable_dns_hostnames = true` is set on the VPC (it is in the Terraform config).

**split_managed (Azure) — PostgreSQL FQDN not resolving:**

The private DNS zone must be linked to the VNet. Verify in the Azure portal under **Private DNS zones → dmarc-prod.postgres.database.azure.com → Virtual network links**. The link should show status `Completed`.

---

### Container fails to start

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-api --tail 50
```

Common causes:
- Missing `SECRET_KEY` or `ENCRYPTION_KEY` in `.env.prod`
- `DATABASE_URL` credentials don't match the database user/password
- For split topologies: database host not reachable (see Database connectivity above)
- ECR/ACR image not yet available (first pipeline run hasn't completed)

### 502 Bad Gateway

The API container is not yet healthy. Wait 30 seconds and retry. If persistent:
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs dmarc-prod-api --tail 20
```

### ECR pull fails on EC2 (AWS)

The EC2 IAM instance profile grants ECR read access without stored credentials:
```bash
aws ecr describe-repositories --region us-east-1
```
If this fails, the instance profile may not be attached. Check **EC2 → Instances → dmarc-prod-app-ec2 → IAM role** in the AWS console.

### ACR pull fails on Azure VM

The managed identity must have the AcrPull role on the ACR:
```bash
az login --identity --output none
az acr login --name dmarcprodacr
```
If this fails, verify the role assignment in the Azure portal: **Container registries → dmarcprodacr → Access control (IAM)**.

### ClamAV not accepting connections

First-start download takes 2–5 minutes. Monitor:
```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-clamav --tail 30
```
Expected when ready: `clamd: pid=1: OK`

### SSM deployment not completing (AWS)

```bash
aws ssm list-command-invocations \
  --instance-id <EC2_INSTANCE_ID> \
  --details --query "CommandInvocations[0]"
```

Verify the SSM agent is running:
```bash
sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent
```

### Azure Run Command not completing

```bash
az vm run-command show \
  --resource-group dmarc-prod-rg \
  --vm-name dmarc-prod-vm \
  --run-command-id RunShellScript
```

Verify the VM is running and the managed identity has the required permissions.

### Reports not being processed

```bash
docker compose -f docker-compose.prod.yml logs dmarc-prod-watcher --tail 50
docker exec dmarc-prod-watcher ls /app/data/reports/incoming/
```

The client slug in the directory name must exactly match the slug in the database.

---

### Linode: StackScript did not run

Docker may not be installed if the StackScript failed on first boot. Check the boot log:

```bash
cat /var/log/stackscript.log
```

If Docker is missing, install it manually:

```bash
curl -fsSL https://get.docker.com | bash
systemctl enable --now docker
mkdir -p /opt/dmarc
```

### Linode: split_vm — cannot reach DB over VPC

Confirm the DB Linode's VPC interface is active and the app Linode's interface is up:

```bash
# On the app Linode — should resolve to a 10.8.0.x address
ip addr show | grep "10.8.0"

# Test PostgreSQL reachability over VPC (replace with DB VPC IP from terraform output db_host)
nc -zv 10.8.0.x 5432
```

If the VPC interface is missing, the instance may have been created before the VPC subnet was ready. Taint the instance and re-apply:

```bash
terraform taint module.compute.linode_instance.app
terraform apply
```

### Linode: split_managed — managed PostgreSQL not accepting connections

Linode Managed Databases enforce an IP allow list. Verify the app Linode's public IP matches the `allow_list` entry:

```bash
# From the app Linode — confirm public IP
curl -s https://checkip.amazonaws.com

# Update the allow list if the IP has changed:
terraform apply   # re-applies the allow_list from app_public_ip output
```

Managed PostgreSQL requires SSL. If connecting via `psql`:

```bash
psql "host=<managed-db-host> port=5432 dbname=<db> user=<user> sslmode=require"
```

### Linode: registry pull fails

Docker Hub has rate limits for unauthenticated pulls (100/6h). Always authenticate before pulling:

```bash
docker login docker.io -u "<username>"
```

For GitHub Container Registry, ensure the PAT has `read:packages` scope and the package visibility is set to match (public or private with auth).

---

## Appendix A — Estimated Monthly Infrastructure Costs

> **Prices are approximate as of mid-2025. All figures are USD, pay-as-you-go / on-demand rates, US East region, with ClamAV enabled (the default configuration). Verify current rates before budgeting.**
>
> Excluded from all estimates: egress data transfer beyond free/included allowances, DNS hosting fees, GitHub Actions compute (free on public repositories / included minutes on private), MaxMind GeoIP subscription (~$24/yr for GeoLite2 via the free tier, $0 for offline mmdb), and SSL certificates (Let's Encrypt = free).

---

### Summary — total estimated monthly cost

| | `standalone` | `split_vm` | `split_managed` |
|---|---|---|---|
| **AWS** | ~$69 | ~$119 | ~$116 |
| **Azure** | ~$73 | ~$126 | ~$134 |
| **Linode** | ~$48 | ~$60 | ~$78 |

The NAT Gateway is the dominant cost driver in split topologies on AWS and Azure (~$33/mo). Linode does not require a NAT Gateway — VPC interfaces are additive, so the DB Linode retains its own public IP for outbound traffic.

---

### AWS — detailed breakdown (us-east-1, on-demand)

#### `standalone`

| Resource | Type | Unit price | Qty | $/mo |
|---|---|---|---|---|
| EC2 — app | t3.large (2 vCPU / 8 GB) | $0.0832/hr | 730 hr | $60.74 |
| EBS — app | gp3, 100 GB | $0.08/GB | 100 GB | $8.00 |
| Elastic IP | Associated to instance | $0.00 | — | $0.00 |
| **Total** | | | | **~$69** |

> Without ClamAV (`clamav_enabled = false`): use t3.medium at $0.0416/hr → **~$38/mo**

#### `split_vm`

| Resource | Type | Unit price | Qty | $/mo |
|---|---|---|---|---|
| EC2 — app | t3.large | $0.0832/hr | 730 hr | $60.74 |
| EC2 — DB | t3.small (2 vCPU / 2 GB) | $0.0208/hr | 730 hr | $15.18 |
| EBS — app | gp3, 100 GB | $0.08/GB | 100 GB | $8.00 |
| EBS — DB | gp3, 30 GB | $0.08/GB | 30 GB | $2.40 |
| Elastic IP | Associated | $0.00 | — | $0.00 |
| NAT Gateway | Hourly fee | $0.045/hr | 730 hr | $32.85 |
| NAT Gateway | Data processed | $0.045/GB | ~0 GB† | ~$0.00 |
| **Total** | | | | **~$119** |

#### `split_managed` (RDS PostgreSQL)

| Resource | Type | Unit price | Qty | $/mo |
|---|---|---|---|---|
| EC2 — app | t3.large | $0.0832/hr | 730 hr | $60.74 |
| EBS — app | gp3, 100 GB | $0.08/GB | 100 GB | $8.00 |
| Elastic IP | Associated | $0.00 | — | $0.00 |
| RDS — db | db.t3.micro (2 vCPU / 1 GB), Single-AZ | $0.017/hr | 730 hr | $12.41 |
| RDS storage | gp2, 20 GB | $0.115/GB | 20 GB | $2.30 |
| NAT Gateway | Hourly | $0.045/hr | 730 hr | $32.85 |
| **Total** | | | | **~$116** |

> Multi-AZ RDS doubles the instance cost (~$25/mo). For DMARC data volumes, Single-AZ with automated backups is typically sufficient.

---

### Azure — detailed breakdown (East US, pay-as-you-go)

#### `standalone`

| Resource | Type | Unit price | Qty | $/mo |
|---|---|---|---|---|
| VM — app | Standard_B2ms (2 vCPU / 8 GB) | $0.0832/hr | 730 hr | $60.74 |
| Managed disk — app | Standard SSD E10 (128 GB tier) | — | 128 GB | $9.60 |
| Static Public IP | Standard SKU | $0.004/hr | 730 hr | $2.92 |
| **Total** | | | | **~$73** |

> Without ClamAV: Standard_B2s at $0.0416/hr → **~$43/mo**

#### `split_vm`

| Resource | Type | Unit price | Qty | $/mo |
|---|---|---|---|---|
| VM — app | Standard_B2ms | $0.0832/hr | 730 hr | $60.74 |
| VM — DB | Standard_B1ms (1 vCPU / 2 GB) | $0.0207/hr | 730 hr | $15.11 |
| Managed disk — app | Standard SSD E10 (128 GB) | — | 128 GB | $9.60 |
| Managed disk — DB | Standard SSD E4 (32 GB) | — | 32 GB | $4.94 |
| Static Public IP | Standard SKU | $0.004/hr | 730 hr | $2.92 |
| NAT Gateway | Hourly | $0.045/hr | 730 hr | $32.85 |
| **Total** | | | | **~$126** |

#### `split_managed` (PostgreSQL Flexible Server)

| Resource | Type | Unit price | Qty | $/mo |
|---|---|---|---|---|
| VM — app | Standard_B2ms | $0.0832/hr | 730 hr | $60.74 |
| Managed disk — app | Standard SSD E10 (128 GB) | — | 128 GB | $9.60 |
| Static Public IP | Standard SKU | $0.004/hr | 730 hr | $2.92 |
| PG Flexible Server | Burstable Standard_B1ms (1 vCPU / 2 GB) | $0.0336/hr | 730 hr | $24.53 |
| PG storage | 32 GB | $0.115/GB | 32 GB | $3.68 |
| NAT Gateway | Hourly | $0.045/hr | 730 hr | $32.85 |
| **Total** | | | | **~$134** |

> Azure PG Flexible Server is more expensive than RDS at equivalent specs. The Burstable tier is sufficient for DMARC report volumes but is not recommended for workloads with sustained high CPU.

---

### Linode — detailed breakdown (us-east, monthly flat rate)

Linode pricing is a flat monthly rate. Each instance includes SSD storage and a generous outbound transfer allowance — no separate disk or transfer line items for typical DMARC volumes.

#### `standalone`

| Resource | Type | Included | $/mo |
|---|---|---|---|
| Linode — app | g6-standard-4 (4 vCPU / 8 GB RAM / 160 GB SSD) | 4 TB/mo transfer | $48.00 |
| **Total** | | | **~$48** |

> Without ClamAV: g6-standard-2 (2 vCPU / 4 GB / 80 GB SSD, 4 TB transfer) → **~$24/mo**

#### `split_vm`

| Resource | Type | Included | $/mo |
|---|---|---|---|
| Linode — app | g6-standard-4 (4 vCPU / 8 GB / 160 GB) | 4 TB/mo transfer | $48.00 |
| Linode — DB | g6-standard-1 (1 vCPU / 2 GB / 50 GB) | 2 TB/mo transfer | $12.00 |
| NAT Gateway | Not required — VPC is additive | — | $0.00 |
| **Total** | | | **~$60** |

#### `split_managed` (Linode Managed PostgreSQL)

| Resource | Type | Included | $/mo |
|---|---|---|---|
| Linode — app | g6-standard-4 (4 vCPU / 8 GB / 160 GB) | 4 TB/mo transfer | $48.00 |
| Managed PostgreSQL | Single node, 2 GB plan | Automated backups | ~$30.00 |
| NAT Gateway | Not required | — | $0.00 |
| **Total** | | | **~$78** |

> Linode Managed PostgreSQL pricing has evolved with the Akamai acquisition. Verify the current node pricing at **linode.com/pricing/#databases** before provisioning. The $30 estimate reflects a single-node 2 GB plan; HA configurations (3 nodes) cost approximately 3×.

---

### Reserved instance savings (AWS and Azure)

Committing to a 1-year term (no upfront payment) reduces compute costs by approximately 30–40% on both AWS and Azure. Linode offers only flat monthly pricing with no reserved option.

| Platform | Topology | On-demand | 1-year reserved | Monthly saving |
|---|---|---|---|---|
| AWS | standalone | ~$69 | ~$47 | ~$22 |
| AWS | split_vm | ~$119 | ~$86 | ~$33 |
| AWS | split_managed | ~$116 | ~$82 | ~$34 |
| Azure | standalone | ~$73 | ~$50 | ~$23 |
| Azure | split_vm | ~$126 | ~$91 | ~$35 |
| Azure | split_managed | ~$134 | ~$98 | ~$36 |
| Linode | all | flat rate | — | — |

> Reserved savings apply to EC2/VM and RDS/PG instance hours only. NAT Gateway, storage, and data transfer remain on-demand pricing.

---

### Data transfer costs

Outbound data transfer is billed separately on AWS and Azure and is not included in the estimates above. For typical DMARC deployments (dashboard access by a small team, API traffic) expect 5–20 GB/mo outbound.

| Platform | Free / included | Overage |
|---|---|---|
| **AWS** | 100 GB/mo free to internet | $0.09/GB (us-east-1) |
| **Azure** | 100 GB/mo free | $0.087/GB (Zone 1) |
| **Linode** | 4 TB/mo included per g6-standard-4 | $0.01/GB |

Linode's included transfer pool is shared across all Linodes in the account, making transfer costs a non-issue for this workload.

---

### Pricing references

- AWS: https://aws.amazon.com/ec2/pricing/on-demand/ · https://aws.amazon.com/rds/postgresql/pricing/
- Azure: https://azure.microsoft.com/en-us/pricing/calculator/
- Linode: https://www.linode.com/pricing/