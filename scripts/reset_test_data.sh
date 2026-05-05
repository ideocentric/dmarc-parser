#!/usr/bin/env bash
# reset_test_data.sh — Wipe DMARC report data for retesting without a full stack restart.
#
# Clears:
#   - flags, auth_results, records, reports, processed_files (allows reingestion)
#   - ip_whois_cache (forces fresh WHOIS lookups on next ingest)
#   - docker-data/reports/incoming/ and archive/ for the specified clients
#
# Preserves:
#   - Clients, domains, users, IMAP config, MFA state
#   - GeoIP database (geoip/)
#   - Docker stack — containers keep running
#
# Usage:
#   bash scripts/reset_test_data.sh                          # clears all clients
#   bash scripts/reset_test_data.sh acme-test globex-test   # clears specific clients
#
set -euo pipefail

COMPOSE_CMD="docker compose --env-file .env.docker"
DB_EXEC="$COMPOSE_CMD exec -T db psql -U dmarc -d dmarc"

# ---------------------------------------------------------------------------
# Resolve client slugs
# ---------------------------------------------------------------------------

if [ $# -gt 0 ]; then
    SLUGS=("$@")
    echo "Clients to reset: ${SLUGS[*]}"
else
    # No args — clear report files for all known clients
    SLUGS=()
    if [ -d docker-data/reports/incoming ]; then
        for dir in docker-data/reports/incoming/*/; do
            [ -d "$dir" ] && SLUGS+=("$(basename "$dir")")
        done
    fi
    echo "Clients found: ${SLUGS[*]:-none}"
fi

# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------

echo ""
echo "This will permanently delete:"
echo "  • All DMARC reports, records, flags, and auth results"
echo "  • All processed-file tracking (allows reingestion of same files)"
echo "  • The WHOIS cache (forces fresh lookups on next ingest)"
echo "  • Report files in docker-data/reports/ for: ${SLUGS[*]:-all}"
echo ""
read -r -p "Type YES to continue: " confirm
if [ "$confirm" != "YES" ]; then
    echo "Aborted."
    exit 0
fi

# ---------------------------------------------------------------------------
# Clear database tables
# Truncate in dependency order — CASCADE handles any FK chains automatically.
# RESTART IDENTITY resets auto-increment sequences for clean IDs on retest.
# ---------------------------------------------------------------------------

echo ""
echo "[1/2] Clearing database tables..."

$DB_EXEC <<'SQL'
TRUNCATE TABLE
    flags,
    auth_results,
    records,
    reports,
    processed_files,
    ip_whois_cache
RESTART IDENTITY CASCADE;
SQL

echo "  ✓ Tables cleared and sequences reset"

# ---------------------------------------------------------------------------
# Remove report files
# ---------------------------------------------------------------------------

echo ""
echo "[2/2] Removing report files..."

for slug in "${SLUGS[@]}"; do
    incoming="docker-data/reports/incoming/$slug"
    archive="docker-data/reports/archive/$slug"

    if [ -d "$incoming" ]; then
        find "$incoming" -type f \( -name "*.xml.gz" -o -name "*.zip" \) -delete
        echo "  ✓ Cleared incoming: $incoming"
    fi

    if [ -d "$archive" ]; then
        rm -rf "${archive:?}/"
        echo "  ✓ Cleared archive:  $archive"
    fi
done

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo "Reset complete. The stack is still running."
echo ""
echo "Reingest sample data:"
echo "  bash sample-data/acme-test/drop_files.sh  docker-data/reports/incoming/acme-test"
echo "  bash sample-data/globex-test/drop_files.sh docker-data/reports/incoming/globex-test"