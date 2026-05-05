# Testing Guide

This document describes the testing strategy for the DMARC Intelligence Platform — what types of tests exist, when to run each, and how to set up the required environments. It is the starting point for contributors and CI/CD engineers.

For the step-by-step functional test checklist see [`FUNCTIONAL_TESTING.md`](../FUNCTIONAL_TESTING.md) at the project root.

---

## Table of Contents

- [Testing Layers](#testing-layers)
- [Unit Tests](#unit-tests)
- [Functional Tests](#functional-tests)
- [Sample Test Data](#sample-test-data)
- [CI/CD Integration](#cicd-integration)
- [Known Gaps and Limitations](#known-gaps-and-limitations)

---

## Testing Layers

The platform uses three distinct testing layers. Each has a different scope, speed, and environment requirement.

| Layer | Tool | Environment | Speed | What it proves |
|-------|------|-------------|-------|----------------|
| **Unit tests** | pytest | In-memory SQLite, no Docker | Fast (~50 s) | Individual service functions and API endpoints behave correctly in isolation |
| **Functional tests** | Manual checklist + Docker | Full Docker stack + PostgreSQL | Slow (30–60 min) | The integrated system works end-to-end: ingestion, intelligence rules, UI, RBAC, multi-tenancy |
| **Manual smoke tests** | Browser + curl | Docker or local dev | Minutes | Quick sanity check after a focused change |

Run unit tests on every commit. Run the full functional suite before a release or after a significant change to ingestion, authentication, or intelligence rules.

---

## Unit Tests

### Quick reference

```bash
# Activate the virtualenv first
source .venv/bin/activate

# Run all tests
pytest

# Run a specific file
pytest tests/test_auth.py -v

# Run tests matching a keyword
pytest -k "offboard"

# Show stdout (useful for debugging)
pytest -s
```

### Environment requirements

Unit tests use an in-memory SQLite database and do not require Docker, PostgreSQL, or a running API server. Two environment variables must be set — either in `.env` or exported in the shell:

```bash
export SECRET_KEY="any-string-at-least-32-chars-long"
export ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

`tests/conftest.py` sets these from `os.environ.setdefault` before importing application code, so the test runner picks them up automatically if they are present in `.env`.

### Test coverage

| File | What it covers |
|------|----------------|
| `tests/test_auth.py` | Login, HttpOnly refresh-token cookie, token refresh, `/auth/me`, password flows |
| `tests/test_users.py` | User CRUD, role management, cross-client data disclosure prevention |
| `tests/test_imap_fetcher.py` | IMAP polling and credential encryption/decryption |
| `tests/test_client_offboard.py` | `build_export_zip` and `purge_client` service functions — 32 unit tests covering ZIP structure, row counts, credential redaction, cascade deletion, orphaned-user deactivation, multi-client user preservation, and filesystem cleanup |
| `tests/test_client_offboard_api.py` | Export and purge HTTP endpoints — 21 tests covering auth enforcement (403/401), response format, slug confirmation validation, control-client isolation |
| `tests/test_parser.py` | DMARC XML parser — field extraction, date handling, malformed input |
| `tests/test_ingestion_security.py` | Ingestion security — 37 tests covering GZ/ZIP size limits, compression ratio (ZIP bomb), path traversal, spoofed ZIP headers, multi-XML ZIPs, encoding fallback, XML sniff, record/count/timestamp bounds, source IP validation, XXE and billion-laughs blocking, IMAP attachment size/count limits and type rejection, ClamAV call-point integration |
| `tests/test_scanner.py` | ClamAV scanner — 9 tests covering disabled no-op, clean pass, FOUND/ERROR rejection, fail-closed and fail-open behaviour when clamd is unreachable, ping, and missing-package error |

**Total: 162 tests, all passing.**

### Key fixtures (`tests/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `engine` | session | In-memory SQLite engine, all tables created once |
| `setup_db` | function (autouse) | Recreates schema before each test, resets rate-limit storage, patches `mfa_required_for_user` to return `False` so tokens never carry `msr=True` during tests |
| `http_client` | function | HTTPX `TestClient` with `get_db` overridden to use the in-memory DB |

### Notes for writing new tests

- Use `create_test_user()` and `create_test_client()` from `tests/conftest.py` for fixture setup.
- `TestClient.delete()` does not support a request body — use `http_client.request("DELETE", url, json={...})` instead.
- The refresh token is set as an HttpOnly cookie scoped to `/api/auth`. When testing refresh flows, read the cookie from the login response and inject it on the client: `client.cookies.set("refresh_token", login.cookies["refresh_token"])`.

---

## Functional Tests

The full functional test procedure is documented in [`FUNCTIONAL_TESTING.md`](../FUNCTIONAL_TESTING.md). It is a step-by-step checklist with pass/fail checkboxes covering every major feature area.

### Environment

Functional tests require the full Docker stack:

```bash
# Start from a clean state
docker compose down -v && rm -rf docker-data
docker compose --env-file .env.docker up --build -d

# Verify all services are healthy before proceeding
docker compose ps
curl -s http://localhost:8000/health | python3 -m json.tool
```

> **Important:** Always run functional tests against a clean environment. Leftover data from a previous run will cause false positives and failures in deduplication, multi-tenancy, and offboarding phases.

### Phase summary

| Phase | Area | Key checks |
|-------|------|------------|
| 0 | Environment setup | Clean Docker stack, all services healthy, DB migrated |
| 1 | Pre-flight | Health endpoint, migration state, initial login |
| 2 | Configuration | Create test clients, domains, and users via CLI |
| 3 | Report ingestion | File-drop processing, deduplication, client isolation, batch scan |
| 4 | Intelligence rules | All 8 flag types fire on correct sample data; severity and filter UI |
| 5 | GeoIP enrichment | Geo data with and without `GeoLite2-City.mmdb`; `enrich-geo` CLI |
| 6 | UI walkthrough | Login, MFA, Dashboard, Reports, Flags, Analytics, Clients, Users |
| 7 | RBAC | super_admin, client admin (multi/single), viewer — access boundaries |
| 8 | Role management | CLI and UI password reset, role changes, MFA enforcement |
| 9 | API smoke tests | Raw curl calls for auth, reports, flags, analytics endpoints |
| 10 | Multi-tenant isolation | Cross-client 403s; database-level row scoping verification |
| 11 | Reset procedures | Report-only reset, DB-only reset, full reset |
| 12 | Client offboarding | Export ZIP contents, purge cascade, orphaned-user deactivation, CLI equivalents |

### Generating sample data

Sample data must be generated before Phase 3. The generated files use deterministic fake reporter names (Faker, seed 42) and IP addresses sourced from real provider ranges (`tests/ip_table.py`):

```bash
# Generate for both test clients (recommended)
python tests/generate_sample_data.py

# Preview what would be generated without writing
python tests/generate_sample_data.py --client acme-test --domain acme-test.example.com

# Drop files in the correct order (baselines first, then scenarios)
cd sample-data/acme-test && bash drop_files.sh docker-data/reports/incoming/acme-test
cd sample-data/globex-test && bash drop_files.sh docker-data/reports/incoming/globex-test
```

The `drop_files.sh` script inserts a short pause between baseline and scenario files to ensure the volume-spike rule has historical data available when scenario files are processed.

---

## Sample Test Data

Three distinct sources of test data exist. Use the right one for the right purpose.

### Generated sample data (`sample-data/`)

Produced by `tests/generate_sample_data.py`. Contains 10 DMARC report files per client covering every intelligence scenario. Use this for functional testing.

- Deterministic — same seed always produces identical files and reporter names
- Git-ignored — regenerate before each functional test run
- IPs sourced from real provider ranges in `tests/ip_table.py`

### Developer example data (`example-data/`)

A drop zone for real-world `.xml.gz` / `.zip` report files during parser debugging. Not part of the automated test flow.

- Subdirectory contents are git-ignored; only `README.md` and `.gitkeep` placeholders are committed
- Real files placed here may contain actual company names — do not use in demos or screenshots

### IP address table (`tests/ip_table.py`)

A committed static module containing real IPv4 addresses sampled from live SPF/MX records. Generated by `tests/build_ip_table.py` and used by `generate_sample_data.py` to ensure scenario IPs fall within real provider ranges.

Regenerate quarterly or when geo enrichment stops matching expected countries:

```bash
python tests/build_ip_table.py              # refresh all providers
python tests/build_ip_table.py --dry-run    # preview without writing
python tests/build_ip_table.py --provider yahoo  # refresh one provider
```

---

## CI/CD Integration

### Required environment variables

Unit tests need two variables. Set them as CI secrets:

| Variable | Purpose | Example value for CI |
|----------|---------|----------------------|
| `SECRET_KEY` | JWT signing key | Any 32+ character random string |
| `ENCRYPTION_KEY` | Fernet key for credential encryption | Output of `Fernet.generate_key().decode()` |

### Recommended pipeline structure

```yaml
# Example GitHub Actions step structure
- name: Install dependencies
  run: pip install -r requirements.txt

- name: Run unit tests
  env:
    SECRET_KEY: ${{ secrets.CI_SECRET_KEY }}
    ENCRYPTION_KEY: ${{ secrets.CI_ENCRYPTION_KEY }}
  run: pytest --tb=short -q
```

### What cannot run in CI without additional setup

| Test type | Blocker | Workaround |
|-----------|---------|------------|
| Functional tests (Phases 0–12) | Requires Docker Compose stack | Use a self-hosted runner with Docker, or a Docker-in-Docker CI service |
| GeoIP phase (Phase 5) | Requires `GeoLite2-City.mmdb` (MaxMind account + download) | Store the `.mmdb` as a CI artifact or skip Phase 5 in automated runs |
| Screenshot capture | Requires running UI + Playwright Chromium | Run as a separate documentation job, not on every commit |

For most projects, running unit tests in CI on every commit and reserving the full functional suite for pre-release or nightly runs is the right trade-off.

---

## Known Gaps and Limitations

### IPv6 geo-enrichment

`tests/ip_table.py` is IPv4 only. Several scenario files include IPv6 source addresses because real DMARC reports routinely contain them, but MaxMind GeoLite2-City has substantially lower IPv6 coverage than IPv4.

The `geo_anomaly` intelligence rule will not fire for IPv6 source IPs even when the address belongs to a high-risk country. For testing geo-anomaly detection, always use the IPv4 entries in `PROVIDER_IPS["geo_anomaly"]` — these are verified to resolve correctly in GeoLite2-City.

GeoLite2 Commercial editions have better IPv6 coverage but are not free.

### IMAP integration tests

There are no automated tests for live IMAP polling. The `tests/test_imap_fetcher.py` suite tests the fetcher logic against a mocked connection. End-to-end IMAP testing requires a real mailbox and is covered by the manual functional test checklist (Phase 3 variant with IMAP configured).

### Frontend unit tests

There are no frontend unit or component tests. The React UI is covered only by the manual functional checklist (Phase 6) and screenshot capture. Adding Vitest or Playwright component tests is a future improvement.