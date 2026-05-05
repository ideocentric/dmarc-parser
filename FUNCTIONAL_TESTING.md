# DMARC Platform — Functional Test Plan

This document provides a structured, repeatable process for verifying end-to-end functionality of the DMARC Intelligence Platform across all phases from environment startup through role-based access validation.

**Test deliverables referenced here:**

| File | Purpose |
|---|---|
| `tests/generate_sample_data.py` | Generates ready-to-drop DMARC report files covering all intelligence scenarios |
| `tests/api_smoke_test.sh` | Automated curl-based API endpoint verification |

---

## ⚠️ WARNING — Isolated Test Environment Only

> **DO NOT run these procedures against a live or production environment.**
>
> The reset and setup steps in this document **permanently delete all data** —
> including the database, all ingested reports, all user accounts, and all
> configuration. They are designed exclusively for a local Docker test stack
> running on a development machine.
>
> Before executing any reset command, verify you are targeting the correct
> environment:
>
> ```bash
> # Confirm you are looking at the local test stack, not a remote one
> docker compose --env-file .env.docker ps
> cat .env.docker | grep DATABASE_URL
> ```
>
> If either of those shows a remote host or a production database URL, **stop immediately**.

---

## Phase 0 — Clean Environment Setup

**Objective:** Start from a completely clean slate. Run this once before a full
test cycle, or whenever you need to reset back to factory defaults.

> **Skip this phase** if the stack is already running and you only need to add
> data or run a subset of tests. Jump directly to Phase 1.

### 0.1 Tear down any existing stack and wipe all data

This removes all containers, volumes, database content, and report files.
The GeoIP database in `./geoip/` is preserved.

```bash
# Stop and remove containers + volumes
docker compose --env-file .env.docker down -v

# Wipe all persisted data (database, reports, logs)
# The geoip/ directory is intentionally excluded
rm -rf docker-data
```

- [ ] `docker compose ... ps` shows no running containers
- [ ] `docker-data/` directory no longer exists

### 0.2 Build and start the stack

```bash
docker compose --env-file .env.docker up --build -d
```

On first boot the stack automatically:
1. Starts PostgreSQL and waits for it to be healthy
2. Runs all Alembic migrations (`0001` + `0002`)
3. Creates the default `super_admin` user (`admin@example.com` / `changeme123`)
4. Creates the `test-client` account with an incoming report folder

Allow 30–60 seconds for the build and first-boot seed to complete.

```bash
# Watch startup logs until you see "Application startup complete"
docker compose --env-file .env.docker logs -f api
```

- [ ] Log shows `Running Alembic migrations...`
- [ ] Log shows `Alembic upgrade complete`
- [ ] Log shows `Created super_admin`
- [ ] Log shows `Application startup complete`

### 0.3 Verify all services are healthy

```bash
docker compose --env-file .env.docker ps
```

| Service | Expected status |
|---|---|
| `dmarc-test-db-1` | `Up (healthy)` |
| `dmarc-test-api-1` | `Up (healthy)` |
| `dmarc-test-watcher-1` | `Up` |
| `dmarc-test-frontend-1` | `Up` |

```bash
curl -s http://localhost:5010/api/health
```

- [ ] Returns `{"status":"ok",...}`

### 0.4 Paste shell helpers

Paste this block into your terminal. All subsequent commands in this document use these functions.

```bash
compose() { docker compose --env-file .env.docker "$@"; }
api()     { docker compose --env-file .env.docker exec api "$@"; }
mgr()     { docker compose --env-file .env.docker exec api python -m cli.manage "$@"; }
export API_URL="http://localhost:5010/api"
export REPORTS_DIR="./docker-data/reports/incoming"
```

### 0.5 Generate sample data

```bash
python tests/generate_sample_data.py
```

- [ ] `sample-data/acme-test/` created with 10 files + `drop_files.sh`
- [ ] `sample-data/globex-test/` created with 10 files + `drop_files.sh`

The stack is now ready. Continue to Phase 1.

---

## Environment Reference

> **Already set up?** If you have pasted the helpers and the stack is running,
> you do not need this section — skip to the phase you want to run.

Paste the appropriate block into your terminal once at the start of a test session.
All commands in this document use the resulting functions.

> **Why functions instead of variables?**  
> zsh (macOS default) and bash do not word-split variables that contain spaces, so
> `export CMD="docker compose exec api"` followed by `$CMD python ...` fails with
> *command not found*. Shell functions work correctly in both shells.

**Docker (recommended for functional testing):**
```bash
compose() { docker compose --env-file .env.docker "$@"; }
api()     { docker compose --env-file .env.docker exec api "$@"; }
mgr()     { docker compose --env-file .env.docker exec api python -m cli.manage "$@"; }
export API_URL="http://localhost:5010/api"
export REPORTS_DIR="./docker-data/reports/incoming"
```

**Local development:**
```bash
compose() { echo "(no compose in local dev)"; }
api()     { "$@"; }
mgr()     { python -m cli.manage "$@"; }
export API_URL="http://localhost:8000"
export REPORTS_DIR="./data/reports/incoming"
```

**Usage examples:**
```bash
compose ps                                  # docker compose ps
mgr create-client acme-test "Acme Corp"    # run a CLI command in the api container
api alembic current                        # run any command in the api container
```

Paste the appropriate block into your terminal once at the start of a test session.
All commands in this document use the resulting functions.

> **Why functions instead of variables?**  
> zsh (macOS default) and bash do not word-split variables that contain spaces, so
> `export CMD="docker compose exec api"` followed by `$CMD python ...` fails with
> *command not found*. Shell functions work correctly in both shells.

**Docker (recommended for functional testing):**
```bash
compose() { docker compose --env-file .env.docker "$@"; }
api()     { docker compose --env-file .env.docker exec api "$@"; }
mgr()     { docker compose --env-file .env.docker exec api python -m cli.manage "$@"; }
export API_URL="http://localhost:5010/api"
export REPORTS_DIR="./docker-data/reports/incoming"
```

**Local development:**
```bash
compose() { echo "(no compose in local dev)"; }
api()     { "$@"; }
mgr()     { python -m cli.manage "$@"; }
export API_URL="http://localhost:8000"
export REPORTS_DIR="./data/reports/incoming"
```

**Usage examples:**
```bash
compose ps                                  # docker compose ps
mgr create-client acme-test "Acme Corp"    # run a CLI command in the api container
api alembic current                        # run any command in the api container
```

---

## Phase 1 — Pre-flight Verification

**Objective:** Confirm the environment is fully operational before any data is loaded.

### 1.1 Stack health

**Docker:**
```bash
docker compose --env-file .env.docker ps
```

Expected — all four services with `(healthy)` or `Up`:

| Service | Status |
|---|---|
| `dmarc-test-db-1` | Up (healthy) |
| `dmarc-test-api-1` | Up (healthy) |
| `dmarc-test-watcher-1` | Up |
| `dmarc-test-frontend-1` | Up |

**Local dev** — verify three processes are running: `uvicorn`, `python main.py`, `npm run dev`.

### 1.2 Health endpoint

```bash
curl -s $API_URL/health
```

- [ ] Returns `{"status":"ok","version":"0.2.0"}`

### 1.3 Database migration state

**Docker:**
```bash
compose exec db psql -U dmarc -d dmarc -t -c "SELECT version_num FROM alembic_version;"
```

**Local dev:**
```bash
alembic current
```

- [ ] Returns `0002` (migrations `0001` + `0002` both applied)

### 1.4 Initial login

Open `http://localhost:5010` (Docker) or `http://localhost:5173` (local dev).

- [ ] Login page loads
- [ ] Login with `admin@example.com` / `changeme123` succeeds
- [ ] Redirected to Dashboard
- [ ] Header shows client dropdown with `test-client` option

---

## Phase 2 — Initial Test Configuration

**Objective:** Create a controlled multi-client, multi-user environment to support isolation testing.

### 2.1 Create test clients

```bash
mgr create-client acme-test "Acme Corporation"
mgr create-client globex-test "Globex Industries"
```

- [ ] Both clients appear in the Clients page in the UI

### 2.2 Create test domains

```bash
mgr create-domain acme-test mail.acme.com
mgr create-domain globex-test mail.globex.com
```

- [ ] Domains appear under each client's Domains tab in the UI

### 2.3 Create test users

> **Role model:** All non-super-admin users have global role `user`. Access and
> capabilities are determined per-client: `admin` can manage the client and reset
> passwords; `viewer` is read-only but can change their own password.

Create one user for each scenario. You will be prompted for a password — use `Test1234!` for all test users.

```bash
# user with admin access to both clients
mgr create-user admin-multi@example.com user --client acme-test --client-role admin
mgr assign-client admin-multi@example.com globex-test --role admin

# user with admin access to acme-test only
mgr create-user admin-single@example.com user --client acme-test --client-role admin

# viewer scoped to acme-test only
mgr create-user viewer-user@example.com user --client acme-test
# (default --client-role is viewer, so no flag needed)
```

### 2.4 Verify configuration

```bash
mgr list-clients
```

Expected output:
```
  acme-test                Acme Corporation                         [active]
  globex-test              Globex Industries                        [active]
  test-client              Test Client                              [active]
```

- [ ] Three clients listed
- [ ] Log into the UI as `admin-single@example.com` — only `acme-test` in dropdown
- [ ] Log into the UI as `admin-multi@example.com` — both clients in dropdown

---

## Phase 3 — Report Ingestion

**Objective:** Verify the file watcher picks up reports, processes them correctly, and archives them.

> All test data is generated by `tests/generate_sample_data.py` using deterministic fake reporter
> names (Faker seed 42). Major email infrastructure providers (Google, Microsoft, Yahoo, Proofpoint)
> are kept as real names; all other reporters use fake company names. Source IPs come from
> real provider ranges (see `tests/ip_table.py` — sampled from live SPF/MX records).
>
> To test with real-world DMARC files during parser debugging, place `.xml.gz` / `.zip` files
> directly in `example-data/acme-test/` or `example-data/globex-test/` and copy them manually —
> this directory is not part of the automated test flow.

### 3.1 Generate the sample data

Run once from the project root. This creates `sample-data/acme-test/` and `sample-data/globex-test/`
with 10 files each, plus a `drop_files.sh` helper in each folder.

```bash
python tests/generate_sample_data.py
ls -lh sample-data/acme-test/
```

- [ ] `sample-data/acme-test/` contains 9 `.xml.gz` files, 1 `.zip` file, and `drop_files.sh`
- [ ] `sample-data/globex-test/` contains the same structure for domain `globex-demo.com`

### 3.2 Drop a single report and verify processing

Start watching the watcher log in a separate terminal:

```bash
docker compose --env-file .env.docker logs -f watcher
# or (local dev):
# tail -f the terminal running python main.py
```

Drop one baseline file manually:

```bash
cp sample-data/acme-test/google.com\!acme-test.example.com\!*all_pass* \
   $REPORTS_DIR/acme-test/ 2>/dev/null || \
cp "$(ls sample-data/acme-test/google.com\!acme-test.example.com\!*.xml.gz | head -1)" \
   $REPORTS_DIR/acme-test/
```

- [ ] Watcher log shows `Detected new file`
- [ ] Watcher log shows `Ingested report` with 3 records
- [ ] Watcher log shows `intelligence flag(s) created` (new_sender_ip)
- [ ] File is **no longer present** in `$REPORTS_DIR/acme-test/`
- [ ] File appears in `./docker-data/reports/archive/acme-test/YYYY-MM/`

### 3.3 Verify in UI

Log in as `admin-single@example.com`, select `acme-test`.

- [ ] Dashboard: **Total Reports** shows 1
- [ ] Reports page: 1 report listed from `Google LLC`
- [ ] Click report → 3 records with Microsoft 365 IPs, all DKIM `pass` / SPF `pass`

### 3.4 Load all sample data (correct order)

The `drop_files.sh` script drops baseline files first (which the volume spike scenario depends on),
waits 3 seconds, then drops scenario files one at a time.

```bash
# Docker
cd sample-data/acme-test && bash drop_files.sh ../../docker-data/reports/incoming/acme-test
cd ../globex-test       && bash drop_files.sh ../../docker-data/reports/incoming/globex-test

# Local dev
cd sample-data/acme-test && bash drop_files.sh ../../data/reports/incoming/acme-test
cd ../globex-test       && bash drop_files.sh ../../data/reports/incoming/globex-test
```

- [ ] Watcher log processes each file in turn without errors
- [ ] Reports page for `acme-test` shows 10 reports from multiple reporters
- [ ] Reports page for `globex-test` shows 10 reports (domain: `globex-demo.com`)

### 3.5 Deduplication check

Drop the same Google baseline file a second time:

```bash
cp "$(ls sample-data/acme-test/google.com\!acme-test.example.com\!*.xml.gz | head -1)" \
   $REPORTS_DIR/acme-test/
```

- [ ] Watcher log shows `Skipping already-processed file`
- [ ] Report count in UI does not increase

### 3.6 Verify second client isolation

The `globex-test` data is already loaded (or was loaded in step 3.4). Log in as `admin-multi@example.com`.

- [ ] Switching to `globex-test` shows reports for `globex-demo.com` — not `acme-test.example.com`
- [ ] Switching to `acme-test` shows no `globex-demo.com` records

### 3.7 Manual scan (batch processing existing files)

If files already exist in the incoming folder but the watcher missed them:

```bash
mgr scan acme-test
```

- [ ] Returns count of files processed

---

## Phase 4 — Intelligence Rule Verification

**Objective:** Confirm the correct flags are created for each ingestion scenario.

Log in as `admin-single@example.com`, select `acme-test`. Navigate to **Flags**.

### 4.1 Expected flags after loading all sample data

These are the flags produced by the **generated** sample data files. The real-world data in
`example-data/` will add additional `new_sender_ip` and `forwarding_pattern` flags but no
critical or high-severity flags (it is a healthy Microsoft 365 environment).

Reporter names for non-major providers are generated by Faker (seed=42). Run `python tests/generate_sample_data.py` to see the exact filenames produced.

| Sample file (reporter) | Expected flags | Severity |
|---|---|---|
| `google.com` (baseline) | `new_sender_ip` × 3 (2 M365 IPv4 + 1 IPv6) | Low |
| `protection.outlook.com` (baseline) | `new_sender_ip` × 2 (M365 IPs from 40.107.0.0/16) | Low |
| `garcia.net` (baseline, fake mail gateway) | `new_sender_ip` × 2 (M365 IPs from 52.100.0.0/15) | Low |
| `rodriguez.com` (fake email security co.) | `spf_fail`, `forwarding_pattern`, `policy_mismatch`, `new_sender_ip` × 2 | High, Info, Medium, Low |
| `garcia.org` (fake mail gateway) | `dkim_fail`, `policy_mismatch`, `new_sender_ip` | High, Medium, Low |
| `proofpoint.com` | `dkim_spf_both_fail`, `new_sender_ip` (148.163.130.170 / 148.163.0.0/16) | Critical, Low |
| `johnson-davis.com` (fake network security co.) | `dkim_spf_both_fail`, `policy_mismatch`, `new_sender_ip` | Critical, Medium, Low |
| `enterprise.protection.outlook.com` | `volume_spike`, `new_sender_ip` (40.107.12.205 spikes vs baseline ~18) | Medium, Low |
| `yahoo.com` | `dkim_spf_both_fail`, `policy_mismatch`, `new_sender_ip` + `geo_anomaly` (GeoIP only, RU/5.44.42.1) | Critical, Medium, Low |
| `google.com` (ZIP, realistic) | `forwarding_pattern`, `spf_fail` (209.85.134.103), `dkim_spf_both_fail`, `new_sender_ip` × 4 | Info, High, Critical, Low |

### 4.2 Flag filter verification

On the Flags page:

- [ ] **Severity filter: Critical** — shows only `dkim_spf_both_fail` entries
- [ ] **Severity filter: High** — shows `spf_fail` and `dkim_fail` entries
- [ ] **Open only toggle** — hides acknowledged flags
- [ ] Total flag count is non-zero

### 4.3 Flag acknowledgement

- [ ] Click **Acknowledge** on any flag — row dims and shows acknowledged user email
- [ ] Toggle **Open only** — acknowledged flag disappears from list
- [ ] Click **Reopen** — flag returns to open state

---

## Phase 5 — GeoIP Enrichment

**Objective:** Verify geo data is populated when the GeoIP database is available.

### 5.1 Without GeoIP database

If `geoip/GeoLite2-City.mmdb` is not present:

```bash
docker compose --env-file .env.docker logs watcher | grep -i geo
```

- [ ] Log shows `GeoIP database not found ... geo rules disabled (optional)` at INFO level (not WARNING)
- [ ] Analytics page: country column shows `—` for all IPs
- [ ] Reports still process normally — no errors

### 5.2 With GeoIP database

Place `GeoLite2-City.mmdb` in `./geoip/`, then restart:

```bash
docker compose --env-file .env.docker restart api watcher
```

Drop a new report (dedup prevents re-processing existing ones — use a different domain to get fresh checksums):

```bash
python tests/generate_sample_data.py --client acme-test --domain geo-test.example.com --output-dir ./test-new
cp ./test-new/acme-test/*.xml.gz $REPORTS_DIR/acme-test/
```

- [ ] Watcher log shows `GeoIP database loaded (GeoLite2-City) from ...`
- [ ] New records have `geo_country` populated
- [ ] Analytics page shows country codes in Top Sending IPs table
- [ ] `209.85.134.103` (Google Workspace, 209.85.128.0/17) shows country `US`

### 5.3 Enrich existing records

```bash
mgr enrich-geo acme-test
```

- [ ] Output shows `Scanned N record(s) — N updated`
- [ ] Re-check Analytics — all IP rows now show country codes

---

## Phase 6 — UI Walkthrough

**Objective:** Verify every page renders correctly with real data.

Log in as `admin@example.com` (super_admin), select `acme-test`.

### 6.1 Login page (`/login`)

- [ ] Page renders clean with email/password fields
- [ ] Empty submission shows validation error (no network call)
- [ ] Wrong password shows `Invalid email or password.`
- [ ] "Sign in with Microsoft" button visible
- [ ] Correct credentials redirect to Dashboard

### 6.2 Dashboard (`/dashboard`)

- [ ] Four stat cards render with non-zero values
- [ ] "Flags by Severity" card shows at least Critical and High rows
- [ ] "Recent Flags" card shows up to 5 flag rows
- [ ] "View all" link on Recent Flags navigates to Flags page
- [ ] Switching client in header dropdown updates all numbers

### 6.3 Reports list (`/reports`)

- [ ] Table renders with 8 rows for `acme-test`
- [ ] Columns: Domain, Reporter, Period End, Policy, Records
- [ ] Policy badge shown for reports with `quarantine` or `reject`
- [ ] Domain filter input narrows results as typed
- [ ] Clicking a row navigates to report detail
- [ ] Pagination appears if more than 25 reports

### 6.4 Report detail (`/reports/:id`)

Open the `both_fail` report (from `Proofpoint`).

- [ ] Back button returns to reports list
- [ ] Domain, org name, date range displayed in header
- [ ] Policy badge shown
- [ ] Records table shows correct source IP, count, disposition
- [ ] DKIM and SPF result badges are colour-coded (pass = green, fail = red)
- [ ] Flag count column shows non-zero for the failing record
- [ ] Geo country shown if GeoIP is configured
- [ ] `209.85.220.41` (Google) shows `US` in country column

### 6.5 Flags (`/flags`)

- [ ] Table renders with all open flags
- [ ] Severity pill buttons filter the list (Critical, High, Medium, Low, Info, All)
- [ ] "Open only" toggle hides acknowledged flags
- [ ] Detail column shows JSON context (source IP, country etc.)
- [ ] Acknowledge button marks flag and dims row
- [ ] Reopen button restores the flag

### 6.6 Analytics (`/analytics`)

- [ ] Page heading shows client slug
- [ ] Bar chart renders (daily message volume)
- [ ] X-axis shows dates in YYYY-MM-DD format
- [ ] Top Sending IPs table has rows with IP, country, message count, report count, failures
- [ ] Failure column is non-zero for IPs from `spf_fail`, `dkim_fail`, `both_fail` reports
- [ ] Country column populated (if GeoIP configured)

### 6.7 Clients (`/clients`)

Log in as `admin@example.com`.

- [ ] Three client cards rendered (acme-test, globex-test, test-client)
- [ ] Expanding a card shows Domains / IMAP tabs
- [ ] Domains tab shows the domain added in Phase 2
- [ ] "Add Domain" input and button functional — domain appears in list after pressing Enter
- [ ] "New Client" form creates a new client (verify in list and DB)
- [ ] IMAP tab shows "Configure IMAP" button when unconfigured

### 6.8 Users (`/users`)

Log in as `admin@example.com` (super_admin).

- [ ] All four test users listed
- [ ] Global role badges correct (`super_admin` = red, `user` = grey)
- [ ] Client access column shows each user's clients with per-client role badges (`admin` or `viewer`)
- [ ] `(must change password)` label shown in amber next to users with a temporary password
- [ ] **Edit button (pencil icon)** opens a modal with global role selector and per-client role list
  - [ ] Can add/remove client assignments
  - [ ] Can change per-client role between `admin` and `viewer`
  - [ ] Save applies changes immediately
- [ ] **Reset Password button (key icon)** opens a modal
  - [ ] Can enter a new password
  - [ ] "Temporary" checkbox controls whether user must change on next login
- [ ] **Deactivate** marks user as inactive (super_admin only, not shown for your own account)
- [ ] "New User" form (super_admin only) creates a user with per-client role assignments

---

## Phase 7 — Role-Based Access Verification

**Objective:** Confirm each user role sees exactly the data they should.

### 7.1 super_admin (`admin@example.com`)

- [ ] Client dropdown lists all clients (acme-test, globex-test, test-client)
- [ ] Can access Clients and Users pages
- [ ] Can create new clients and users
- [ ] Can edit any user's global role and per-client roles
- [ ] Can reset any user's password
- [ ] Cross-client analytics accessible via `GET /analytics`

### 7.2 Client admin — multi-client (`admin-multi@example.com`)

Global role: `user`. Per-client role: `admin` for both `acme-test` and `globex-test`.

- [ ] Client dropdown lists both `acme-test` and `globex-test`
- [ ] Can switch between both and see their respective data
- [ ] Can access Clients page (view and domain management for their clients)
- [ ] Can access Users page (sees users assigned to their admin clients)
- [ ] **Reset Password button visible** for users in their clients
- [ ] Cannot access `globex-test` data while viewing `acme-test` (reports list only shows acme records)

### 7.3 Client admin — single client (`admin-single@example.com`)

Global role: `user`. Per-client role: `admin` for `acme-test` only.

- [ ] Client dropdown shows only `acme-test`
- [ ] Reports, Flags, Analytics pages show only acme-test data
- [ ] Clients and Users pages visible in sidebar
- [ ] `globex-test` data is not accessible — `403` returned by API

### 7.4 Viewer (`viewer-user@example.com`)

Global role: `user`. Per-client role: `viewer` for `acme-test` only.

- [ ] Client dropdown shows only `acme-test` (or client name shown as static text if only one)
- [ ] Reports, Flags, Analytics pages show only acme-test data
- [ ] Clients and Users pages visible in sidebar (backend enforces access)
- [ ] **No Edit button** in Users page (viewers cannot reset other users' passwords)
- [ ] **Reset Password button visible only for their own account**
- [ ] `globex-test` data is not accessible — `403` returned by API

---

## Phase 8 — Role Management & Password Reset

**Objective:** Verify CLI and UI controls for changing roles and resetting passwords.

### 8.1 Change global role via CLI

```bash
# Elevate viewer-user to check promotion works
mgr set-role viewer-user@example.com super_admin

# Verify
mgr list-clients   # still accessible, super_admin can call any command
```

- [ ] No error returned
- [ ] Log into UI as `viewer-user@example.com` — all clients visible in dropdown

```bash
# Restore to user
mgr set-role viewer-user@example.com user
```

- [ ] After restore, dropdown returns to showing only acme-test

### 8.2 Change per-client role via CLI

```bash
# Promote viewer to admin on acme-test
mgr set-client-role viewer-user@example.com acme-test admin
```

- [ ] Log in as `viewer-user@example.com` — Users page now shows Reset Password buttons for other acme-test users

```bash
# Restore to viewer
mgr set-client-role viewer-user@example.com acme-test viewer
```

- [ ] Reset Password buttons no longer visible for other users

### 8.3 Reset password via CLI (permanent)

```bash
mgr reset-password viewer-user@example.com
# Enter: NewPass456!  (when prompted)
```

- [ ] No error returned
- [ ] Log in as `viewer-user@example.com` with `NewPass456!` succeeds
- [ ] No forced change-password screen (permanent reset)

### 8.4 Reset password via CLI (temporary)

```bash
mgr reset-password admin-single@example.com --temporary
# Enter: TempPass789!  (when prompted)
```

- [ ] Log in as `admin-single@example.com` with `TempPass789!`
- [ ] Immediately redirected to `/change-password` — cannot navigate elsewhere
- [ ] Change Password screen shows "Your password must be changed before continuing"
- [ ] Submitting with wrong current password shows error
- [ ] Submitting mismatched new passwords shows error
- [ ] Submitting valid new password (≥ 8 chars) returns to Dashboard
- [ ] Logging out and logging in again with the new password succeeds — no change-password redirect

### 8.5 Reset password via UI

Log in as `admin@example.com` (super_admin). Navigate to **Users**.

- [ ] Click the key icon next to `viewer-user@example.com`
- [ ] Reset Password modal opens
- [ ] "Temporary — require change on next login" checkbox is checked by default
- [ ] Enter a new password and click Reset Password
- [ ] Modal closes without error
- [ ] Log in as `viewer-user@example.com` with the new password
- [ ] Redirected to `/change-password` (temporary flag was set)
- [ ] Complete the password change — redirected to Dashboard

### 8.6 Edit roles via UI

Log in as `admin@example.com`. Navigate to **Users**.

- [ ] Click the pencil icon next to `viewer-user@example.com`
- [ ] Edit modal opens showing current global role (`user`) and client assignments
- [ ] Change per-client role for `acme-test` from `viewer` to `admin`
- [ ] Click Save
- [ ] User row updates to show `admin` badge for acme-test
- [ ] Log in as `viewer-user@example.com` — Users page now shows management capabilities

Restore for subsequent phases:

```bash
mgr set-client-role viewer-user@example.com acme-test viewer
```

---

## Phase 9 — API Smoke Tests

**Objective:** Verify all key API endpoints programmatically.

Run the smoke test script against your environment:

```bash
# Docker
bash tests/api_smoke_test.sh \
    http://localhost:5010/api \
    admin@example.com \
    changeme123 \
    acme-test

# Local dev
bash tests/api_smoke_test.sh \
    http://localhost:8000 \
    admin@example.com \
    changeme123 \
    acme-test
```

- [ ] All tests report `PASS`
- [ ] No `FAIL` entries in output
- [ ] Exit code is `0`

**Key endpoints covered by the script:**

| Endpoint | Test |
|---|---|
| `GET /health` | 200, body contains `ok` |
| `POST /auth/login` | 200 with valid credentials |
| `POST /auth/login` | 401 with invalid credentials |
| `GET /auth/me` | 200 with token, response includes `must_change_password` |
| `GET /auth/me` | 401/403 without token |
| `POST /auth/refresh` | 200 with refresh token |
| `POST /auth/refresh` | 401 with access token as refresh |
| `GET /clients` | 200, list |
| `GET /clients/{slug}` | 200 |
| `GET /clients/nonexistent` | 404 |
| `GET /clients/{slug}/domains` | 200 |
| `GET /users` | 200 (super_admin) |
| `GET /clients/{slug}/reports` | 200, paginated |
| `GET /clients/{slug}/reports/{id}` | 200, includes records |
| `GET /clients/{slug}/reports/999999` | 404 |
| `GET /clients/{slug}/records` | 200, paginated |
| `GET /clients/{slug}/records?has_flags=true` | 200 |
| `GET /clients/{slug}/flags` | 200, paginated |
| `GET /clients/{slug}/flags?unacknowledged_only=true` | 200 |
| `GET /clients/{slug}/flags?severity=critical` | 200 |
| `GET /clients/{slug}/flags?severity=invalid` | 422 |
| `POST /clients/{slug}/flags/{id}/acknowledge` | 200 |
| `POST /clients/{slug}/flags/{id}/unacknowledge` | 200 |
| `GET /clients/{slug}/analytics` | 200 |
| `GET /analytics` | 200 (super_admin) |

**Additional manual API checks (password & role endpoints):**

```bash
# Obtain a token for these checks
TOKEN=$(curl -s -X POST $API_URL/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

VIEWER_ID=$(curl -s -H "Authorization: Bearer $TOKEN" $API_URL/users \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(u['id']) for u in d if u['email']=='viewer-user@example.com']")

# Reset password — should return 204
curl -s -o /dev/null -w "%{http_code}" \
  -X POST $API_URL/users/$VIEWER_ID/reset-password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"new_password":"TempReset1!","temporary":true}'
```

- [ ] Returns `204`
- [ ] `GET /auth/me` for viewer-user shows `must_change_password: true`

---

## Phase 10 — Multi-tenant Isolation

**Objective:** Confirm that users cannot access another client's data through any means.

### 10.1 Obtain tokens for both users

```bash
# viewer-user@example.com (acme-test only)
VIEWER_TOKEN=$(curl -s -X POST $API_URL/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"viewer-user@example.com","password":"Test1234!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# super_admin token for comparison
ADMIN_TOKEN=$(curl -s -X POST $API_URL/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

> If `viewer-user@example.com` has a `must_change_password` flag set from Phase 8,
> reset it first: `mgr reset-password viewer-user@example.com` (without `--temporary`).

### 10.2 Cross-client API access (expect 403)

```bash
# viewer-user trying to access globex-test reports
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  "$API_URL/clients/globex-test/reports"
```

- [ ] Returns `403` — access denied

```bash
# viewer-user trying to access globex-test flags
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  "$API_URL/clients/globex-test/flags"
```

- [ ] Returns `403`

```bash
# viewer-user listing all clients — should only see their assigned client
curl -s \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  "$API_URL/clients" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Clients visible: {len(d)}')"
```

- [ ] Returns `1` (only their own client)

### 10.3 Database-level verification

**Docker:**
```bash
docker compose --env-file .env.docker exec db \
  psql -U dmarc -d dmarc -c \
  "SELECT c.slug, COUNT(r.id) AS reports
   FROM clients c
   LEFT JOIN reports r ON r.client_id = c.id
   GROUP BY c.slug
   ORDER BY c.slug;"
```

- [ ] Each client slug shows its own report count
- [ ] No reports appear under the wrong client

---

## Phase 11 — Reset Procedures

Use the appropriate reset level depending on what needs to be cleared.

### 11.1 Reset report files only

Clears all incoming and archive files. Database records, flags, and user configuration are preserved.

```bash
# Docker
rm -rf docker-data/reports/incoming docker-data/reports/archive
docker compose --env-file .env.docker up -d
# (entrypoint recreates the directory structure)

# Local dev
rm -rf data/reports/incoming data/reports/archive
mkdir -p data/reports/incoming data/reports/archive
```

### 11.2 Reset database only

Drops and recreates the schema. Report files in `docker-data/reports/` are preserved (already-processed files will be skipped on re-ingest because their checksums no longer exist in the DB — delete them first if you want them re-processed).

**What this clears:**
- All user accounts, TOTP secrets, MFA enrollment, and refresh tokens
- All clients, domains, and IMAP configuration
- All reports, records, flags, and processed-file checksums

**Docker:**
```bash
docker compose --env-file .env.docker exec db \
  psql -U dmarc -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker compose --env-file .env.docker restart api
# Alembic re-runs on next startup; seed re-creates admin@example.com and test-client
```

**Local dev:**
```bash
alembic downgrade base
alembic upgrade head
python -m cli.manage create-user admin@example.com super_admin
python -m cli.manage create-client test-client "Test Client"
```

**After a database reset:**
- [ ] Wait for API to log `Application startup complete`
- [ ] Log in as `admin@example.com` / `changeme123` to confirm seed ran
- [ ] Re-run Phase 2 to recreate test clients, domains, and users
- [ ] Re-run Phase 3 to re-ingest sample reports (or delete archive files first so they are re-processed)
- [ ] If `scripts/.screenshot_state.json` exists, regenerate it: `python scripts/screenshot_accounts.py --rebuild`

### 11.3 Full reset (database + all data)

Wipes everything. Preserves the GeoIP database in `./geoip/`.

**Docker:**
```bash
docker compose --env-file .env.docker down -v
rm -rf docker-data
docker compose --env-file .env.docker up --build -d
```

**After full reset:**
- [ ] Wait for API to log `Application startup complete`
- [ ] Re-run Phase 2 (create clients, domains, users)
- [ ] Re-run Phase 3 (ingest test reports)
- [ ] Re-run `enrich-geo` if GeoIP database is available
- [ ] If `scripts/.screenshot_state.json` exists, regenerate it: `python scripts/screenshot_accounts.py --rebuild`

### 11.4 Reset users and MFA only (keep report data)

Use this when you want fresh user accounts and cleared MFA state without losing ingested report data or client configuration. This truncates only the user-related tables — clients, domains, reports, records, and flags are untouched.

**Docker:**
```bash
docker compose --env-file .env.docker exec db psql -U dmarc -d dmarc -c "
  TRUNCATE refresh_tokens CASCADE;
  TRUNCATE user_clients CASCADE;
  TRUNCATE users CASCADE;
"
docker compose --env-file .env.docker restart api
# Seed re-creates admin@example.com (no MFA, no test users)
```

- [ ] Wait for API to log `Application startup complete`
- [ ] Log in as `admin@example.com` / `changeme123` to confirm the seed account exists

**Recreate standard test users:**

Use the shell helpers from Phase 0.4, then run all user creation in one block. Use `Test1234!` as the password for each when prompted.

```bash
# Phase 2 test users — run after the truncate above
mgr create-user admin-multi@example.com user --client acme-test --client-role admin
mgr assign-client admin-multi@example.com globex-test --role admin

mgr create-user admin-single@example.com user --client acme-test --client-role admin

mgr create-user viewer-user@example.com user --client acme-test
```

- [ ] Log in as each user to confirm access is correct
- [ ] Clients, domains, reports, flags, and analytics are still present and unchanged

**If screenshot accounts are needed:**

```bash
python scripts/screenshot_accounts.py --rebuild
```

This recreates the `screenshot-viewer@example.com` and `screenshot-mfa@example.com` accounts, re-enables TOTP on the MFA account, and writes fresh credentials and the new TOTP secret to `scripts/.screenshot_state.json`.

---

## Phase 12 — Client Offboarding (Export and Purge)

**Objective:** Verify the full offboarding lifecycle: data in place → export → verify export → purge → verify all data gone, control client intact, orphaned users deactivated, multi-client users retain remaining access.

> Run this phase after Phase 3 (report ingestion) so `acme-test` has data to export.
> Requires the stack to be running with the shell helpers from Phase 0 set up.

### 12.1 Create offboarding test users

These users test the three deactivation scenarios.

```bash
# Orphaned viewer — only assigned to acme-test → must be deactivated on purge
mgr create-user orphan-viewer@example.com user --client acme-test --client-role viewer

# Orphaned admin — only assigned to acme-test → must be deactivated on purge
mgr create-user orphan-admin@example.com user --client acme-test --client-role admin

# Multi-client user — assigned to both clients → must stay active, lose acme-test only
mgr create-user multi-client@example.com user --client acme-test --client-role admin
mgr assign-client multi-client@example.com globex-test --role viewer
```

Verify:
- [ ] `orphan-viewer@example.com` can log in and sees only `acme-test`
- [ ] `multi-client@example.com` can log in and sees both `acme-test` and `globex-test`

### 12.2 Capture pre-export DB row counts

Run these queries. Note the values — they become your verification baseline after the purge.

```bash
docker compose --env-file .env.docker exec db psql -U dmarc dmarc -c "
  SELECT
    (SELECT COUNT(*) FROM reports       WHERE client_id = (SELECT id FROM clients WHERE slug='acme-test')) AS reports,
    (SELECT COUNT(*) FROM records       WHERE client_id = (SELECT id FROM clients WHERE slug='acme-test')) AS records,
    (SELECT COUNT(*) FROM flags         WHERE client_id = (SELECT id FROM clients WHERE slug='acme-test')) AS flags,
    (SELECT COUNT(*) FROM domains       WHERE client_id = (SELECT id FROM clients WHERE slug='acme-test')) AS domains,
    (SELECT COUNT(*) FROM user_clients  WHERE client_id = (SELECT id FROM clients WHERE slug='acme-test')) AS user_assignments;
"
```

- [ ] All counts are non-zero
- [ ] Note globex-test counts separately (should be unaffected by purge):

```bash
docker compose --env-file .env.docker exec db psql -U dmarc dmarc -c "
  SELECT COUNT(*) AS globex_reports FROM reports
  WHERE client_id = (SELECT id FROM clients WHERE slug='globex-test');
"
```

### 12.3 Export via UI

1. Log in as `admin@example.com` (super\_admin)
2. Navigate to **Sidebar → Clients** → expand the `acme-test` card
3. Click the **Security** tab
4. Scroll to the **Danger Zone** section
5. Click **Export Data**

- [ ] Browser download starts immediately
- [ ] Filename is `acme-test-export-{YYYY-MM-DD}.zip`
- [ ] File size is greater than 0 bytes

### 12.4 Verify ZIP contents

```bash
# Unzip to a temp directory
unzip ~/Downloads/acme-test-export-*.zip -d /tmp/acme-export-verify
ls /tmp/acme-export-verify/acme-test-export-*/
```

- [ ] `README.txt` present
- [ ] `client.json` present — open and verify `slug == "acme-test"`
- [ ] `domains.csv` present — row count matches 12.2 baseline
- [ ] `users.csv` present — contains `orphan-viewer@example.com`, `orphan-admin@example.com`, `multi-client@example.com`
- [ ] `reports.csv` present — row count matches 12.2 baseline
- [ ] `records.csv` present — row count matches 12.2 baseline
- [ ] `auth_results.csv` present
- [ ] `flags.csv` present — row count matches 12.2 baseline

Verify credential redaction:
```bash
cat /tmp/acme-export-verify/acme-test-export-*/imap_config.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('password:', d.get('password'))"
```
- [ ] Output shows `password: REDACTED`
- [ ] `globex-test` does not appear anywhere in reports.csv or records.csv

### 12.5 Export via CLI

```bash
mgr export-client acme-test --output /tmp/acme-cli-export.zip
```

- [ ] Output: `Export written to: /tmp/acme-cli-export.zip  (NNN bytes)`
- [ ] File exists and is a valid ZIP

### 12.6 Purge via UI

1. Back in the Security tab → Danger Zone section
2. In the **Purge Client** section, type anything other than the slug — confirm the **Purge Client** button stays disabled
3. Type `acme-test` exactly — the **Purge Client** button enables
4. Click **Purge Client**

- [ ] The `acme-test` card disappears from the Clients page immediately
- [ ] No error shown in the browser

### 12.7 Post-purge DB verification — all acme-test data gone

```bash
docker compose --env-file .env.docker exec db psql -U dmarc dmarc -c "
  SELECT
    (SELECT COUNT(*) FROM clients       WHERE slug='acme-test')                                              AS client_exists,
    (SELECT COUNT(*) FROM reports       WHERE client_id NOT IN (SELECT id FROM clients))                     AS orphaned_reports,
    (SELECT COUNT(*) FROM records       WHERE client_id NOT IN (SELECT id FROM clients))                     AS orphaned_records,
    (SELECT COUNT(*) FROM flags         WHERE client_id NOT IN (SELECT id FROM clients))                     AS orphaned_flags;
"
```

- [ ] `client_exists` = **0** — client row deleted
- [ ] `orphaned_reports` = **0**
- [ ] `orphaned_records` = **0**
- [ ] `orphaned_flags` = **0**

### 12.8 Post-purge — control client data intact

```bash
docker compose --env-file .env.docker exec db psql -U dmarc dmarc -c "
  SELECT COUNT(*) AS globex_reports FROM reports
  WHERE client_id = (SELECT id FROM clients WHERE slug='globex-test');
"
```

- [ ] Count matches the pre-purge `globex-test` count from 12.2

### 12.9 Post-purge — user status verification

```bash
docker compose --env-file .env.docker exec db psql -U dmarc dmarc -c "
  SELECT email, is_active FROM users
  WHERE email IN (
    'orphan-viewer@example.com',
    'orphan-admin@example.com',
    'multi-client@example.com',
    'admin@example.com'
  )
  ORDER BY email;
"
```

- [ ] `admin@example.com` — `is_active = t` (super\_admin unaffected)
- [ ] `multi-client@example.com` — `is_active = t` (has other client)
- [ ] `orphan-admin@example.com` — `is_active = f` (only had acme-test)
- [ ] `orphan-viewer@example.com` — `is_active = f` (only had acme-test)

Verify multi-client user UI:
- [ ] Log in as `multi-client@example.com` — succeeds
- [ ] Only `globex-test` in client dropdown — `acme-test` is gone

Verify orphaned users are locked out:
- [ ] Attempt to log in as `orphan-viewer@example.com` — login fails (account disabled)

### 12.10 Post-purge — filesystem directories removed

```bash
ls docker-data/reports/incoming/acme-test 2>&1
ls docker-data/reports/archive/acme-test  2>&1
```

- [ ] Both return `No such file or directory`

```bash
ls docker-data/reports/incoming/globex-test
ls docker-data/reports/archive/globex-test
```

- [ ] Both directories exist (control client unaffected)

### 12.11 CLI purge on a disposable client

Verify the interactive CLI flow:

```bash
mgr create-client purge-cli-test "CLI Purge Test"
mgr purge-client purge-cli-test
# When prompted: type something wrong → expect "Slug did not match — aborted."
# Re-run and type purge-cli-test → purge proceeds
```

- [ ] Wrong slug input aborts cleanly
- [ ] Correct slug input shows deletion summary
- [ ] `mgr list-clients` no longer shows `purge-cli-test`

Non-interactive (scripting) mode:

```bash
mgr create-client purge-cli-test2 "CLI Purge Test 2"
mgr purge-client purge-cli-test2 --yes
```

- [ ] Purge completes without prompt
- [ ] Summary output shows all row counts

### 12.12 Seed script re-creates test-client after restart

```bash
docker compose --env-file .env.docker restart api
docker compose --env-file .env.docker logs api --tail 10
```

- [ ] Log shows `Test client exists : test-client` (not re-created since it was never purged)

To verify re-creation works: do a full reset (Phase 0) and confirm the seed script creates it fresh.

---

## Phase 13 — Ingestion Security (Malformed, Corrupt, and Malicious Files)

**Objective:** Verify the ingestion pipeline safely rejects oversized, malformed, and crafted files and produces appropriate log output at WARNING or ERROR level for operator review.

> Requires the stack to be running. Use the shell helpers from Phase 0.4.
> All tests use the `acme-test` client drop folder unless noted.

### 13.1 Oversized GZ file

Create a GZ file whose decompressed content exceeds the 50 MB limit:

```bash
# Generate 51 MB of repeated bytes and compress them
python3 -c "import gzip, sys; sys.stdout.buffer.write(gzip.compress(b'x' * 51_000_000))" \
  > /tmp/oversized.xml.gz

cp /tmp/oversized.xml.gz docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY][acme-test] GZ decompressed size exceeded 50 MB limit`
- [ ] Log includes filename and compressed size in bytes
- [ ] No report or record created in the database
- [ ] File is **not** moved to the archive (pipeline returned False)

### 13.2 ZIP bomb (high compression ratio)

Create a ZIP with a compression ratio above 100:1:

```bash
python3 -c "
import gzip, io, zipfile
# 5 MB of repeated bytes compresses to ~5 KB — ratio ~1000:1
data = b'A' * 5_000_000
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('report.xml', data)
open('/tmp/bomb.zip', 'wb').write(buf.getvalue())
"
cp /tmp/bomb.zip docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY]` and `compression ratio` with the computed ratio
- [ ] Log includes compressed and decompressed sizes
- [ ] No report created

### 13.3 ZIP with path traversal entry

```bash
python3 -c "
import zipfile, io
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as zf:
    info = zipfile.ZipInfo('../../etc/passwd.xml')
    zf.writestr(info, b'<evil/>')
open('/tmp/traversal.zip', 'wb').write(buf.getvalue())
"
cp /tmp/traversal.zip docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY]` and `path traversal attempt`
- [ ] Log includes the offending entry name
- [ ] No report created

### 13.4 ZIP with multiple XML entries

```bash
python3 -c "
import zipfile, io
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as zf:
    zf.writestr('first.xml', b'<?xml version=\"1.0\"?><feedback/>')
    zf.writestr('second.xml', b'<other/>')
open('/tmp/multi.zip', 'wb').write(buf.getvalue())
"
cp /tmp/multi.zip docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY]` warning listing the ignored entries
- [ ] First XML entry is processed (report attempt made, even if XML is minimal)
- [ ] Second entry is silently skipped

### 13.5 Malformed XML (not well-formed)

```bash
python3 -c "
import gzip
data = gzip.compress(b'<?xml version=\"1.0\"?><feedback><unclosed>')
open('/tmp/malformed.xml.gz', 'wb').write(data)
"
cp /tmp/malformed.xml.gz docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows an error for the file with the parse exception detail
- [ ] No report created

### 13.6 XXE injection attempt

```bash
python3 -c "
import gzip
xxe = b'''<?xml version=\"1.0\"?>
<!DOCTYPE feedback [
  <!ENTITY xxe SYSTEM \"file:///etc/passwd\">
]>
<feedback>&xxe;</feedback>'''
open('/tmp/xxe.xml.gz', 'wb').write(gzip.compress(xxe))
"
cp /tmp/xxe.xml.gz docker-data/reports/incoming/acme-test/
```

- [ ] File is rejected — watcher log shows a parse error
- [ ] `/etc/passwd` content does **not** appear anywhere in logs or database
- [ ] No report created

### 13.7 Report with excessive record count

```bash
python3 -c "
import gzip, textwrap
record = '''
  <record>
    <row><source_ip>1.2.3.4</source_ip><count>1</count>
      <policy_evaluated><disposition>none</disposition><dkim>pass</dkim><spf>pass</spf></policy_evaluated>
    </row>
    <identifiers><header_from>example.com</header_from></identifiers>
    <auth_results><dkim><domain>example.com</domain><result>pass</result></dkim></auth_results>
  </record>'''
records = record * 10_001
xml = f'''<?xml version=\"1.0\"?><feedback>
  <report_metadata><org_name>Test</org_name><email>t@t.com</email>
    <report_id>overcount</report_id>
    <date_range><begin>1746057600</begin><end>1746143999</end></date_range>
  </report_metadata>
  <policy_published><domain>example.com</domain><p>none</p><pct>100</pct></policy_published>
  {records}
</feedback>'''
open('/tmp/overcount.xml.gz', 'wb').write(gzip.compress(xml.encode()))
"
cp /tmp/overcount.xml.gz docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY]` rejection with record count and limit
- [ ] No report created

### 13.8 IMAP — oversized attachment

If IMAP is configured for `acme-test`, send a test email with an attachment larger than 25 MB. The simplest test using the API:

```bash
# Verify the limit is in effect by checking the log after a real oversized attachment arrives
# Look for:
docker compose --env-file .env.docker logs api | grep "SECURITY.*exceeds"
```

- [ ] Log shows `[SECURITY][acme-test] uid=... attachment ... size ... bytes exceeds limit`
- [ ] No report created for the oversized attachment

### 13.9 Log review after all security tests

```bash
docker compose --env-file .env.docker logs api 2>&1 | grep "\[SECURITY\]"
```

- [ ] Every test from 13.1–13.8 that should produce a `[SECURITY]` log entry appears
- [ ] Each entry includes: client slug, filename (or uid), reason, and relevant sizes/counts
- [ ] No `[SECURITY]` entries reference actual content of the rejected files (no data exfiltration via logs)

### 13.10 ClamAV — verify daemon is running (prerequisite for 13.11–13.12)

> Skip steps 13.10–13.12 if ClamAV is not enabled (`CLAMAV_ENABLED=false`).
> To enable, see `docs/deployment-guide.md — ClamAV Antivirus Scanning`.

```bash
# Confirm clamd is reachable from the API container
docker compose --env-file .env.docker exec api python3 -c \
  "from ingestion.scanner import ping; print('ClamAV OK' if ping() else 'ClamAV UNREACHABLE')"
```

- [ ] Output is `ClamAV OK`
- [ ] API startup log contains `ClamAV scanning enabled — connecting to clamd at ...`

### 13.11 ClamAV — EICAR test string detected and rejected

The EICAR test file is an industry-standard inert string universally detected by antivirus software. It is safe to use and contains no actual malware.

```bash
# Create the EICAR test string as a GZ file
python3 -c "
import gzip
# Standard EICAR test string — detected as 'Eicar-Test-Signature' by ClamAV
eicar = b'X5O!P%@AP[4\x5cPZX54(P^)7CC)7}\$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!\$H+H*'
data = gzip.compress(eicar)
open('/tmp/eicar.xml.gz', 'wb').write(data)
print('Created /tmp/eicar.xml.gz')
"

cp /tmp/eicar.xml.gz docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY] MALWARE DETECTED in eicar.xml.gz — ClamAV signature: Eicar-Test-Signature`
- [ ] No report or record created in the database
- [ ] File is not archived

### 13.12 ClamAV — fail-closed behaviour when clamd is unreachable

> This test requires temporarily stopping clamd. Restore it after the test.

```bash
# Stop the ClamAV service (Docker: stop the container; bare-metal: stop the daemon)
docker compose --env-file .env.docker stop clamav    # Docker
# OR: sudo systemctl stop clamav-daemon               # bare-metal

# Drop a legitimate report (should be rejected because clamd is down and CLAMAV_FAIL_OPEN=false)
cp sample-data/acme-test/google.com\!*.xml.gz \
   docker-data/reports/incoming/acme-test/
```

- [ ] Watcher log shows `[SECURITY] ClamAV unavailable for ... CLAMAV_FAIL_OPEN=false, rejecting file`
- [ ] No report created despite the file being legitimate
- [ ] Restore ClamAV: `docker compose --env-file .env.docker start clamav`
- [ ] After restart, re-drop the same file and confirm it is processed normally

---

## Appendix — Test Data Reference

### Developer example data (`example-data/`)

`example-data/acme-test/` and `example-data/globex-test/` are **not part of the automated test
flow**. They are empty drop zones for developers to place real-world DMARC report files when
debugging parser issues or verifying compatibility with a specific mail provider's format.

To use: copy `.xml.gz` or `.zip` files into the appropriate folder and drop them into the
incoming directory manually:

```bash
cp example-data/acme-test/*.xml.gz $REPORTS_DIR/acme-test/
```

These files are git-ignored and never included in generated test data runs.

### Generated sample data (`tests/generate_sample_data.py`)

Run `python tests/generate_sample_data.py` to create `sample-data/`. Each client gets 10 files
covering all intelligence rule scenarios. The script also writes a `drop_files.sh` helper that
drops files in the correct order (baselines first, then scenarios).

Reporter names are generated deterministically using Faker (default seed 42). Major public email
providers (Google, Microsoft, Yahoo, Proofpoint) are kept as real names. All other reporters use
seeded fake company names — the same seed always produces the same names. Use `--seed <int>` to
change them.

| File (reporter domain) | Scenario | Key flags triggered |
|---|---|---|
| `google.com!...` (BASELINE) | All pass, 3 M365 IPs | `new_sender_ip` ×3 |
| `protection.outlook.com!...` (BASELINE) | All pass; seeds history for volume spike IP | `new_sender_ip` ×2 |
| `<fake>.net!...!sampledata` (BASELINE) | All pass, 2 records from fake mail gateway reporter | `new_sender_ip` ×2 |
| `<fake>.com!...` | Forwarding: SPF fail + DKIM pass, `p=quarantine` | `spf_fail`, `forwarding_pattern`, `policy_mismatch` |
| `<fake>.org!...` | DKIM fail only (SPF passes), `p=reject` | `dkim_fail`, `policy_mismatch` |
| `proofpoint.com!...` | Both fail, `p=quarantine`, quarantined | `dkim_spf_both_fail` |
| `<fake>.com!...` | Both fail, `p=reject`, disposition overridden to none | `dkim_spf_both_fail`, `policy_mismatch` |
| `enterprise.protection.outlook.com!...` | Volume spike: 200 msgs from IP seen at avg 18 | `volume_spike` |
| `yahoo.com!...` | Both fail from Russian IP 5.44.42.1 | `dkim_spf_both_fail`, `geo_anomaly`* |
| `google.com!...` (ZIP) | Realistic mix: bulk pass + forwarding + both fail | `forwarding_pattern`, `spf_fail`, `dkim_spf_both_fail` |

\* `geo_anomaly` only fires if GeoLite2-City.mmdb is present and `enrich-geo` has run.

Run `python tests/generate_sample_data.py` to see the actual fake reporter names for your seed.

### Flag severity reference

| Severity | Colour | Meaning |
|---|---|---|
| `critical` | Red | Both DKIM and SPF failed — strong evidence of spoofing or misconfiguration |
| `high` | Orange | Single auth failure |
| `medium` | Yellow | Disposition/policy inconsistency, or geo anomaly |
| `low` | Blue | Informational — new sender IP seen for the first time |
| `info` | Grey | Pattern detected (forwarding, policy override) — not necessarily harmful |

### Role reference

| Global role | Per-client role | Description |
|---|---|---|
| `super_admin` | (N/A — full access) | Manages all clients, all users, system configuration |
| `user` | `admin` | Manages the assigned client: domains, IMAP, user password resets |
| `user` | `viewer` | Read-only access to assigned client data; can change own password |

### Default test accounts

| Email | Password | Global role | Per-client role | Clients |
|---|---|---|---|---|
| `admin@example.com` | `changeme123` | `super_admin` | (all) | All |
| `admin-multi@example.com` | `Test1234!` | `user` | `admin` | acme-test, globex-test |
| `admin-single@example.com` | `Test1234!` | `user` | `admin` | acme-test |
| `viewer-user@example.com` | `Test1234!` | `user` | `viewer` | acme-test |

### CLI command reference

| Command | Description |
|---|---|
| `mgr create-user <email> <role> [--client <slug>] [--client-role admin\|viewer]` | Create user with optional first client assignment |
| `mgr set-role <email> <role>` | Change global role (`super_admin` or `user`) |
| `mgr assign-client <email> <slug> [--role admin\|viewer]` | Grant client access (default: viewer) |
| `mgr set-client-role <email> <slug> <role>` | Change per-client role for existing assignment |
| `mgr revoke-client <email> <slug>` | Remove client access |
| `mgr reset-password <email> [--temporary]` | Set new password; `--temporary` forces change on next login |
| `mgr list-clients` | List all clients with status |
| `mgr scan <slug>` | Process any unprocessed files in incoming folder |
| `mgr enrich-geo <slug> [--force]` | Backfill GeoIP data for existing records |
| `mgr enrich-whois <slug> [--force]` | Backfill WHOIS/RDAP ownership data for existing records |
| `mgr export-client <slug> [--output <path>]` | Export all client data to a ZIP file (JSON/CSV) |
| `mgr purge-client <slug> [--yes]` | Permanently delete all data for a client |