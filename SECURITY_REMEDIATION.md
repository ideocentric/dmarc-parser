# Security Remediation Tracker

Audit date: 2026-05-02  
Status key: `[ ]` todo · `[~]` in progress · `[x]` done

---

## CRITICAL

### [x] CRIT-1 — XML/XXE: unsafe parser on email-sourced input
**File:** `ingestion/parser.py:56`  
**Risk:** Billion Laughs entity expansion from a malicious DMARC XML attachment crashes ingestion.

**Fix:**
```bash
# Add to requirements.txt
defusedxml>=0.7.1
```
```python
# ingestion/parser.py — replace
import defusedxml.ElementTree as ET
root = ET.fromstring(xml_string)   # replaces xml.etree.ElementTree.fromstring()
```
Also add a file size cap (e.g. 50 MB) in `ingestion/extractor.py` before calling the parser.

---

### [x] CRIT-2 — Insecure defaults: JWT secret + encryption key can be empty
**Files:** `core/config.py:11,24` · `core/crypto.py:22`  
**Risk:** Default JWT secret is a known string → forgeable `super_admin` tokens. Empty encryption key → IMAP passwords stored in plaintext.

**Fix — `core/config.py`:** Remove default values so startup fails without env vars:
```python
secret_key: str          # was: = "dev-secret-change-me"
encryption_key: str      # was: = ""
```
**Fix — `core/crypto.py`:** Raise hard error instead of silent fallback:
```python
def _get_fernet():
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY must be set before starting the server")
```
**Fix — `api/main.py`:** Add a startup validation hook that asserts both values are set and non-default.

---

### [x] CRIT-3 — `python-jose` has unpatched CVEs (library abandoned)
**File:** `requirements.txt`  
**CVEs:** CVE-2024-33664, CVE-2024-33663 (CVSS 9.8) — JWT algorithm confusion, RSA→HMAC key substitution.  
**Risk:** Attacker can forge arbitrary JWTs. No upstream fix exists; library unmaintained since 2023.

**Fix:** Migrate to `joserfc` or `PyJWT`.
```bash
pip install joserfc   # or: pip install PyJWT
pip uninstall python-jose
```
Update all imports in `api/auth/jwt.py` and anywhere `jose` is imported. Rewrite `create_access_token`, `create_refresh_token`, `decode_token` to use the new library's API.

---

## HIGH

### [x] HIGH-1 — Path traversal via client slug in filesystem paths
**Files:** `core/config.py:51` · `api/routes/clients.py:28` · `cli/manage.py:51`  
**Risk:** `slug="../other-client"` redirects ingestion pipeline across tenants; `slug="../../etc"` creates directories at arbitrary locations.

**Fix — `core/schemas/client.py`:** Add validator to `ClientCreate`:
```python
import re
from pydantic import field_validator

@field_validator("slug")
@classmethod
def slug_safe(cls, v: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", v):
        raise ValueError("slug must be lowercase alphanumeric with hyphens, 2–63 chars")
    return v
```
**Fix — `core/config.py`:** Assert constructed path stays under base dir:
```python
def client_incoming_dir(self, slug: str) -> Path:
    result = (self.incoming_dir / slug).resolve()
    if not str(result).startswith(str(self.incoming_dir.resolve())):
        raise ValueError("slug escapes base directory")
    return result
```
Apply same pattern to `client_archive_dir`.

---

### [x] HIGH-2 — Zip Slip: ZIP entry names not validated
**File:** `ingestion/extractor.py:24`  
**Risk:** A ZIP entry named `../../somewhere` passes current filters; any future disk-write path would be exploitable immediately.

**Fix:**
```python
import posixpath

for n in zf.namelist():
    safe = posixpath.normpath(n)
    if safe.startswith("..") or safe.startswith("/"):
        raise ValueError(f"Suspicious path in ZIP: {n}")
    if n.lower().endswith(".xml"):
        xml_names.append(n)
```

---

### [x] HIGH-3 — No rate limiting on login / refresh endpoints
**File:** `api/routes/auth.py:23,31`  
**Risk:** Unlimited credential-stuffing against all accounts. 30-day refresh token has no revocation — a stolen token is valid for a full month.

**Fix (rate limiting):**
```bash
pip install slowapi
```
Apply `@limiter.limit("5/minute")` to `POST /auth/login` and `POST /auth/refresh` using the client IP as the key.

**Fix (token rotation):** Create a `refresh_tokens` table (`id`, `jti`, `user_id`, `expires_at`). On each `/auth/refresh`: validate JTI exists in table, delete the old entry, insert a new one. On logout: delete the entry.

---

### [x] HIGH-4 — Refresh token in `localStorage` (XSS-accessible)
**Files:** `frontend/src/api/client.ts:6,17` · `frontend/src/contexts/AuthContext.tsx:43`  
**Risk:** Any JavaScript on the page (including injected via compromised dependency) can steal the 30-day refresh token.

**Fix:** Issue the refresh token as an `HttpOnly; Secure; SameSite=Strict` cookie from the backend. The frontend never touches it — the browser sends it automatically. Keep only the short-lived access token in memory (not `localStorage`).

Backend: `response.set_cookie("refresh_token", token, httponly=True, secure=True, samesite="strict", max_age=30*86400)`  
Frontend: remove `localStorage.setItem("refreshToken", ...)` — read access token only from memory/state.

---

### [x] HIGH-5 — SSRF: user-controlled IMAP host not validated
**Files:** `api/routes/imap.py:53` · `core/schemas/imap.py:15`  
**Risk:** Client admin points `host` at `169.254.169.254` or internal IPs, triggering outbound TCP from the server.

**Fix — `core/schemas/imap.py`:** Validate host rejects private/loopback addresses:
```python
import ipaddress, socket
from pydantic import field_validator

@field_validator("host")
@classmethod
def no_ssrf_host(cls, v):
    if v is None:
        return v
    try:
        addr = ipaddress.ip_address(socket.gethostbyname(v))
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError("IMAP host resolves to a private/internal address")
    except socket.gaierror:
        pass  # unknown hostname — let the connection fail naturally
    return v
```
Also constrain `port` to a reasonable range (e.g., 143, 993, or 1024–65535).

---

### [x] HIGH-6 — Azure OAuth `code` + `state` sent as URL query parameters
**Files:** `api/routes/auth.py:74` · `frontend/src/api/auth.ts:39`  
**Risk:** Authorization code appears in server access logs, browser history, and `Referer` headers.

**Fix — backend:** Accept `code`/`state` in the POST body:
```python
class AzureCallbackRequest(BaseModel):
    code: str
    state: str

@router.post("/azure/callback", response_model=TokenResponse)
def azure_callback(body: AzureCallbackRequest, db: Session = Depends(get_db)):
    claims = exchange_code(body.code, body.state)
    ...
```
**Fix — frontend:** Send as JSON body rather than query string.

---

### [x] HIGH-7 — Vite dev server path traversal (CVE-2025-30208, CVE-2025-31125)
**File:** `frontend/package.json` — `vite ^5.4.10`  
**Risk:** Path traversal via `?import&raw` / `?url` on exposed Vite dev server. Affects < 5.4.15.

**Fix:**
```json
"vite": "^5.4.15"
```
```bash
npm install
```

---

### [x] HIGH-8 — `cryptography` pin allows CVE-vulnerable versions
**File:** `requirements.txt` — `>=42.0.0`  
**CVE:** CVE-2024-26130 (CVSS 7.5) — NULL pointer dereference in PKCS12 parsing in 42.0.0–42.0.3.

**Fix:**
```
cryptography>=42.0.4
```
Or upgrade to latest: `cryptography>=44.0.0`

---

## MEDIUM

### [x] MED-1 — Azure OAuth state stored in process memory (breaks multi-worker)
**File:** `api/auth/azure.py:19`  
**Risk:** In multi-worker/Kubernetes deployments the worker validating the callback may not hold the state, bypassing CSRF protection.

**Fix:** Replace the in-memory `_pending_states` dict with a Redis key (TTL 10 min) or a short-lived DB table. The comment in the file already acknowledges this.

---

### [x] MED-2 — `flag_type` query param has no allowlist or length limit
**File:** `api/routes/flags.py:29`  
**Risk:** No SQL injection (ORM is parameterised), but inconsistent with the `severity` allowlist pattern directly above it.

**Fix:** Define `FLAG_TYPES` as a set and validate, or add `max_length=64` to the `Query()`:
```python
flag_type: str | None = Query(None, max_length=64)
```

---

### [x] MED-3 — Raw exception message returned to client on IMAP poll failure
**File:** `api/routes/imap.py:151`  
**Risk:** IMAP/OAuth error strings can leak internal hostnames, network topology, partial credentials.

**Fix:**
```python
log.error("[%s] IMAP poll error: %s", client.slug, exc, exc_info=True)
raise HTTPException(status_code=502, detail="IMAP poll failed — check server logs")
```

---

### [x] MED-4 — `DomainCreate.domain` has no RFC 1123 format validation
**File:** `core/schemas/client.py:26`  
**Risk:** Accepts `"../evil"`, bare IPs, un-normalised IDNs — logic errors in DMARC matching.

**Fix:**
```python
@field_validator("domain")
@classmethod
def valid_domain(cls, v: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+", v):
        raise ValueError("Invalid domain name")
    return v.lower()
```

---

### [x] MED-5 — World atlas TopoJSON fetched from CDN at runtime
**File:** `frontend/src/components/shared/GeoDistributionMap.tsx:7`  
**Risk:** Supply-chain risk if jsDelivr or `world-atlas` npm package is compromised; also leaks user IP to CDN.

**Fix:**
```bash
cp node_modules/world-atlas/countries-110m.json public/countries-110m.json
```
```typescript
// GeoDistributionMap.tsx
const GEO_URL = "/countries-110m.json";
```

---

### [x] MED-6 — Azure SSO auto-provisions accounts as active without admin approval
**File:** `api/routes/auth.py:87`  
**Risk:** Any user in the Azure tenant gets a valid session without an admin creating their account first.

**Fix (recommended):** Provision new SSO accounts as `is_active=False` and require admin activation. Or add a `AZURE_AUTO_PROVISION` config flag defaulting to `false`:
```python
user = User(..., is_active=settings.azure_auto_provision)
```

---

## LOW

### [x] LOW-1 — No refresh token revocation (logout is client-side only)
**File:** `api/auth/jwt.py:23`  
**Note:** Largely addressed by HIGH-3 (token rotation table). Once HIGH-3 is implemented, deleting the DB row on logout completes this fix.

### [x] LOW-2 — `must_change_password` enforced on frontend only
**File:** `api/routes/auth.py` / `api/deps.py`  
**Fix:** Add a FastAPI dependency that checks `current_user.must_change_password` and raises HTTP 403 with code `"password_change_required"` for all endpoints except `/auth/change-password` and `/auth/me`.

### [x] LOW-3 — Email change accepted without verification
**File:** `api/routes/users.py:149`  
**Fix:** At minimum, log old + new email on change. Ideally send a verification link to the new address before committing the update.

### [x] LOW-4 — CLI password prompts echo input to terminal
**File:** `cli/manage.py:85,206`  
**Fix:** Replace `input("Password: ")` with `getpass.getpass("Password: ")`.

---

## Confirmed Safe — No Action Required

| Area | Status |
|------|--------|
| SQL injection | ORM used with parameterised queries throughout — no raw SQL with user input |
| Command injection | No `subprocess`, `os.system`, `eval()`, or `shell=True` found |
| XSS | All user data rendered via JSX text nodes (auto-escaped) — no `dangerouslySetInnerHTML` |
| IMAP secret exposure | `ImapConfigRead` correctly omits `encrypted_password` and `oauth2_client_secret` |
| Multi-tenant IDOR | `get_accessible_client()` applied consistently; all queries filter by resolved `client_id` |

---

## Suggested Fix Order for a Single Session

1. `LOW-4` — 2 min: swap `input()` for `getpass()`
2. `CRIT-2` — 15 min: remove insecure defaults; add startup validation
3. `CRIT-1` — 20 min: add `defusedxml` and file size cap
4. `HIGH-7` — 2 min: bump Vite version
5. `HIGH-8` — 2 min: tighten `cryptography` pin
6. `HIGH-1` + `HIGH-2` — 30 min: slug regex validator + ZIP entry check
7. `MED-3` — 5 min: sanitise IMAP error response
8. `MED-4` — 10 min: domain format validator
9. `MED-5` — 5 min: bundle world atlas file locally
10. `CRIT-3` — 60 min+: migrate off `python-jose` (requires rewriting JWT module)
11. `HIGH-3` + `LOW-1` — 90 min: rate limiting + refresh token rotation table
12. `HIGH-4` — 60 min: move refresh token to `HttpOnly` cookie
13. `HIGH-5` — 20 min: IMAP host SSRF validation
14. `HIGH-6` — 30 min: OAuth code → POST body
15. Remaining medium/low items