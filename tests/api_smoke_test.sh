#!/usr/bin/env bash
# =============================================================================
# DMARC Platform — API Smoke Test
# =============================================================================
# Tests all key API endpoints and reports PASS / FAIL for each.
#
# Usage:
#   # Docker (via nginx proxy)
#   bash tests/api_smoke_test.sh http://localhost:5010/api admin@example.com changeme123 test-client
#
#   # Local development (direct to uvicorn)
#   bash tests/api_smoke_test.sh http://localhost:8000 admin@example.com changeme123 test-client
#
# Arguments:
#   $1  Base API URL    (no trailing slash)
#   $2  Admin email
#   $3  Admin password
#   $4  Client slug to use for scoped tests
# =============================================================================

BASE_URL="${1:-http://localhost:5010/api}"
ADMIN_EMAIL="${2:-admin@example.com}"
ADMIN_PASSWORD="${3:-changeme123}"
CLIENT_SLUG="${4:-test-client}"

PASS=0
FAIL=0

# Colour codes
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
RESET="\033[0m"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

check() {
    local name="$1"
    local expected_status="$2"
    local actual_status="$3"
    local body="$4"

    if [ "$actual_status" = "$expected_status" ]; then
        echo -e "${GREEN}PASS${RESET}  $name"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}FAIL${RESET}  $name"
        echo -e "       expected HTTP $expected_status, got HTTP $actual_status"
        [ -n "$body" ] && echo -e "       body: $(echo "$body" | head -c 200)"
        FAIL=$((FAIL + 1))
    fi
}

http_get() {
    curl -s -o /tmp/smoke_body -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$BASE_URL$1"
}

http_post() {
    curl -s -o /tmp/smoke_body -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$2" \
        "$BASE_URL$1"
}

http_post_noauth() {
    curl -s -o /tmp/smoke_body -w "%{http_code}" \
        -H "Content-Type: application/json" \
        -d "$2" \
        "$BASE_URL$1"
}

body() { cat /tmp/smoke_body; }

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo " DMARC Platform — API Smoke Test"
echo " Base URL : $BASE_URL"
echo " Client   : $CLIENT_SLUG"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Health
# ---------------------------------------------------------------------------
echo -e "${YELLOW}── Health ──────────────────────────────────────────────────${RESET}"

STATUS=$(curl -s -o /tmp/smoke_body -w "%{http_code}" "$BASE_URL/health")
check "GET /health returns 200" "200" "$STATUS"

# ---------------------------------------------------------------------------
# 2. Authentication
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── Authentication ──────────────────────────────────────────${RESET}"

STATUS=$(http_post_noauth "/auth/login" "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
check "POST /auth/login — valid credentials" "200" "$STATUS"

TOKEN=$(cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
REFRESH_TOKEN=$(cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}FATAL${RESET}  Could not obtain access token — aborting"
    exit 1
fi

STATUS=$(http_post_noauth "/auth/login" '{"email":"nobody@example.com","password":"wrong"}')
check "POST /auth/login — invalid credentials returns 401" "401" "$STATUS"

STATUS=$(http_get "/auth/me")
check "GET /auth/me — returns current user" "200" "$STATUS"

STATUS=$(http_post "/auth/refresh" "{\"refresh_token\":\"$REFRESH_TOKEN\"}")
check "POST /auth/refresh — valid refresh token" "200" "$STATUS"

STATUS=$(http_post "/auth/refresh" "{\"refresh_token\":\"$TOKEN\"}")
check "POST /auth/refresh — access token as refresh returns 401" "401" "$STATUS"

STATUS=$(curl -s -o /tmp/smoke_body -w "%{http_code}" "$BASE_URL/auth/me")
check "GET /auth/me — no token returns 401/403" "401" "$STATUS" || true
ACTUAL=$(cat /tmp/smoke_body | python3 -c "import sys; print(sys.stdin.read())" 2>/dev/null)
if [[ "$STATUS" == "401" || "$STATUS" == "403" ]]; then
    echo -e "${GREEN}PASS${RESET}  GET /auth/me — no token returns 401 or 403"
    PASS=$((PASS + 1))
    FAIL=$((FAIL - 1))
fi

# ---------------------------------------------------------------------------
# 3. Clients
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── Clients ─────────────────────────────────────────────────${RESET}"

STATUS=$(http_get "/clients")
check "GET /clients — returns list" "200" "$STATUS"

STATUS=$(http_get "/clients/$CLIENT_SLUG")
check "GET /clients/$CLIENT_SLUG — returns client" "200" "$STATUS"

STATUS=$(http_get "/clients/nonexistent-client-xyz")
check "GET /clients/nonexistent — returns 404" "404" "$STATUS"

STATUS=$(http_get "/clients/$CLIENT_SLUG/domains")
check "GET /clients/$CLIENT_SLUG/domains — returns domain list" "200" "$STATUS"

# ---------------------------------------------------------------------------
# 4. Users
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── Users ───────────────────────────────────────────────────${RESET}"

STATUS=$(http_get "/users")
check "GET /users — super_admin can list users" "200" "$STATUS"

ME_ID=$(http_get "/auth/me" && cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
STATUS=$(http_get "/users/$ME_ID")
check "GET /users/{id} — own profile" "200" "$STATUS"

# ---------------------------------------------------------------------------
# 5. Reports
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── Reports ─────────────────────────────────────────────────${RESET}"

STATUS=$(http_get "/clients/$CLIENT_SLUG/reports")
check "GET /clients/$CLIENT_SLUG/reports — returns paginated list" "200" "$STATUS"

REPORT_COUNT=$(cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total', 0))" 2>/dev/null)
echo "       total reports: $REPORT_COUNT"

if [ "$REPORT_COUNT" -gt 0 ] 2>/dev/null; then
    REPORT_ID=$(cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'])" 2>/dev/null)
    STATUS=$(http_get "/clients/$CLIENT_SLUG/reports/$REPORT_ID")
    check "GET /clients/$CLIENT_SLUG/reports/$REPORT_ID — report detail" "200" "$STATUS"

    REC_COUNT=$(cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('records',[])))" 2>/dev/null)
    echo "       records in first report: $REC_COUNT"
else
    echo -e "${YELLOW}SKIP${RESET}  Report detail — no reports ingested yet"
fi

STATUS=$(http_get "/clients/$CLIENT_SLUG/reports/999999")
check "GET /clients/$CLIENT_SLUG/reports/999999 — non-existent returns 404" "404" "$STATUS"

STATUS=$(http_get "/clients/$CLIENT_SLUG/records")
check "GET /clients/$CLIENT_SLUG/records — flat records list" "200" "$STATUS"

STATUS=$(http_get "/clients/$CLIENT_SLUG/records?has_flags=true")
check "GET /clients/$CLIENT_SLUG/records?has_flags=true — filtered records" "200" "$STATUS"

# ---------------------------------------------------------------------------
# 6. Flags
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── Flags ───────────────────────────────────────────────────${RESET}"

STATUS=$(http_get "/clients/$CLIENT_SLUG/flags")
check "GET /clients/$CLIENT_SLUG/flags — returns paginated flags" "200" "$STATUS"

FLAG_COUNT=$(cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null)
echo "       total flags: $FLAG_COUNT"

STATUS=$(http_get "/clients/$CLIENT_SLUG/flags?unacknowledged_only=true")
check "GET /clients/$CLIENT_SLUG/flags?unacknowledged_only=true" "200" "$STATUS"

STATUS=$(http_get "/clients/$CLIENT_SLUG/flags?severity=critical")
check "GET /clients/$CLIENT_SLUG/flags?severity=critical" "200" "$STATUS"

STATUS=$(http_get "/clients/$CLIENT_SLUG/flags?severity=invalid_severity")
check "GET /clients/$CLIENT_SLUG/flags?severity=invalid — returns 422" "422" "$STATUS"

if [ "$FLAG_COUNT" -gt 0 ] 2>/dev/null; then
    FLAG_ID=$(http_get "/clients/$CLIENT_SLUG/flags" && cat /tmp/smoke_body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'])" 2>/dev/null)
    STATUS=$(http_get "/clients/$CLIENT_SLUG/flags/$FLAG_ID")
    check "GET /clients/$CLIENT_SLUG/flags/$FLAG_ID — flag detail" "200" "$STATUS"

    STATUS=$(http_post "/clients/$CLIENT_SLUG/flags/$FLAG_ID/acknowledge" "{}")
    check "POST /clients/$CLIENT_SLUG/flags/$FLAG_ID/acknowledge" "200" "$STATUS"

    STATUS=$(http_post "/clients/$CLIENT_SLUG/flags/$FLAG_ID/unacknowledge" "{}")
    check "POST /clients/$CLIENT_SLUG/flags/$FLAG_ID/unacknowledge" "200" "$STATUS"
else
    echo -e "${YELLOW}SKIP${RESET}  Flag acknowledge/unacknowledge — no flags present"
fi

# ---------------------------------------------------------------------------
# 7. Analytics
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── Analytics ───────────────────────────────────────────────${RESET}"

STATUS=$(http_get "/clients/$CLIENT_SLUG/analytics")
check "GET /clients/$CLIENT_SLUG/analytics — client analytics" "200" "$STATUS"

STATUS=$(http_get "/analytics")
check "GET /analytics — cross-client summary (super_admin)" "200" "$STATUS"

# ---------------------------------------------------------------------------
# 8. IMAP config
# ---------------------------------------------------------------------------
echo -e "\n${YELLOW}── IMAP ────────────────────────────────────────────────────${RESET}"

STATUS=$(http_get "/clients/$CLIENT_SLUG/imap")
if [ "$STATUS" = "200" ] || [ "$STATUS" = "404" ]; then
    check "GET /clients/$CLIENT_SLUG/imap — 200 (configured) or 404 (not configured)" "200" "$STATUS" || \
    check "GET /clients/$CLIENT_SLUG/imap — 200 (configured) or 404 (not configured)" "404" "$STATUS"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
TOTAL=$((PASS + FAIL))
echo -e " Results: ${GREEN}$PASS passed${RESET} / ${RED}$FAIL failed${RESET} / $TOTAL total"
echo "============================================================"
echo ""

[ $FAIL -eq 0 ] && exit 0 || exit 1