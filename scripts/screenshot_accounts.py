#!/usr/bin/env python3
"""
Set up test accounts required for automated screenshot capture.

Idempotent — safe to run multiple times. Use --rebuild to wipe and reset
all test account state from scratch (useful after significant auth changes).

Usage:
    python scripts/screenshot_accounts.py [options]

Options:
    --base-url URL        Platform URL (default: http://localhost:5010)
    --admin-email EMAIL   Super-admin email (default: admin@example.com)
    --admin-password PASS Super-admin password (default: changeme123)
    --client-slug SLUG    Client to assign test accounts to (default: acme-test)
    --rebuild             Reset all test account state before setup
    --state-file PATH     Where to save credentials + MFA secret
                          (default: scripts/.screenshot_state.json)

After running, the state file contains everything capture_screenshots.py needs.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
import pyotp

DEFAULT_VIEWER_EMAIL = "screenshot-viewer@example.com"
DEFAULT_VIEWER_PASS = "ScreenshotViewer1!"
DEFAULT_MFA_EMAIL = "screenshot-mfa@example.com"
DEFAULT_MFA_PASS = "ScreenshotMfa1!"

API_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _api(base_url: str) -> str:
    return base_url.rstrip("/") + "/api"


def _login(api: str, email: str, password: str, mfa_secret: str | None = None) -> str:
    """Return an access token. Handles MFA automatically if mfa_secret is given."""
    r = httpx.post(f"{api}/auth/login", json={"email": email, "password": password},
                   timeout=API_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("mfa_required"):
        if not mfa_secret:
            raise RuntimeError(f"MFA required for {email} but no secret provided")
        code = pyotp.TOTP(mfa_secret).now()
        r2 = httpx.post(f"{api}/auth/mfa/verify",
                        json={"mfa_token": data["mfa_token"], "code": code},
                        timeout=API_TIMEOUT)
        r2.raise_for_status()
        return r2.json()["access_token"]
    return data["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_users(api: str, token: str) -> list[dict]:
    r = httpx.get(f"{api}/users", headers=_headers(token), timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _find_user(users: list[dict], email: str) -> dict | None:
    return next((u for u in users if u["email"] == email), None)


def _create_user(api: str, token: str, email: str, password: str,
                 client_slug: str, client_role: str = "viewer") -> dict:
    payload = {
        "email": email,
        "password": password,
        "role": "user",
        "client_roles": [{"slug": client_slug, "role": client_role}],
    }
    r = httpx.post(f"{api}/users", json=payload, headers=_headers(token), timeout=API_TIMEOUT)
    r.raise_for_status()
    print(f"  Created user: {email}")
    return r.json()


def _reset_password(api: str, token: str, user_id: int, new_password: str) -> None:
    r = httpx.post(f"{api}/users/{user_id}/reset-password",
                   json={"new_password": new_password, "temporary": False},
                   headers=_headers(token), timeout=API_TIMEOUT)
    r.raise_for_status()
    print(f"  Reset password for user ID {user_id}")


def _reactivate_user(api: str, token: str, user_id: int) -> None:
    r = httpx.patch(f"{api}/users/{user_id}",
                    json={"is_active": True},
                    headers=_headers(token), timeout=API_TIMEOUT)
    r.raise_for_status()


def _setup_mfa(api: str, token: str) -> str:
    """Call /auth/mfa/setup and return the TOTP secret extracted from the URI."""
    r = httpx.post(f"{api}/auth/mfa/setup", headers=_headers(token), timeout=API_TIMEOUT)
    r.raise_for_status()
    uri = r.json()["otpauth_uri"]
    match = re.search(r"secret=([A-Z2-7]+)", uri)
    if not match:
        raise RuntimeError(f"Could not extract secret from otpauth URI: {uri}")
    return match.group(1)


def _confirm_mfa(api: str, token: str, secret: str) -> None:
    """Confirm MFA setup with a live TOTP code (retries once on clock boundary)."""
    totp = pyotp.TOTP(secret)
    for attempt in range(3):
        code = totp.now()
        r = httpx.post(f"{api}/auth/mfa/confirm", json={"code": code},
                       headers=_headers(token), timeout=API_TIMEOUT)
        if r.status_code == 204:
            return
        if r.status_code == 401 and attempt < 2:
            print("  TOTP code rejected (clock boundary?) — waiting for next window...")
            time.sleep(31)
            continue
        r.raise_for_status()


def _disable_mfa(api: str, token: str, secret: str) -> None:
    """Disable MFA using a live TOTP code."""
    totp = pyotp.TOTP(secret)
    for attempt in range(3):
        code = totp.now()
        r = httpx.post(f"{api}/auth/mfa/disable", json={"code": code},
                       headers=_headers(token), timeout=API_TIMEOUT)
        if r.status_code == 204:
            return
        if r.status_code == 401 and attempt < 2:
            time.sleep(31)
            continue
        r.raise_for_status()


def _check_client_exists(api: str, token: str, slug: str) -> bool:
    r = httpx.get(f"{api}/clients", headers=_headers(token), timeout=API_TIMEOUT)
    r.raise_for_status()
    return any(c["slug"] == slug for c in r.json())


# ---------------------------------------------------------------------------
# Main setup logic
# ---------------------------------------------------------------------------

def setup(args: argparse.Namespace) -> None:
    api = _api(args.base_url)
    state_file = Path(args.state_file)

    print(f"\n── DMARC Screenshot Account Setup ──")
    print(f"  API:    {api}")
    print(f"  Client: {args.client_slug}")
    print(f"  Rebuild: {args.rebuild}")

    # Load existing state if present
    state: dict = {}
    if state_file.exists() and not args.rebuild:
        state = json.loads(state_file.read_text())
        print(f"  Loaded existing state from {state_file}")

    # --- Admin token ---
    print("\n[1/4] Authenticating as super_admin...")
    admin_token = _login(api, args.admin_email, args.admin_password)
    print("  OK")

    # --- Verify client exists ---
    print(f"\n[2/4] Checking client '{args.client_slug}' exists...")
    if not _check_client_exists(api, admin_token, args.client_slug):
        print(f"  ERROR: Client '{args.client_slug}' not found.")
        print("  Run: docker compose --env-file .env.docker exec api "
              f"python -m cli.manage create-client {args.client_slug} 'Test Client'")
        print("  Then drop sample data and try again.")
        sys.exit(1)
    print("  OK")

    users = _get_users(api, admin_token)

    # --- Viewer account ---
    print(f"\n[3/4] Setting up viewer account ({args.viewer_email})...")
    viewer = _find_user(users, args.viewer_email)

    if viewer and args.rebuild:
        print("  --rebuild: resetting viewer account")
        _reset_password(api, admin_token, viewer["id"], args.viewer_password)
        _reactivate_user(api, admin_token, viewer["id"])
    elif viewer:
        print("  Already exists — skipping creation")
        if not viewer["is_active"]:
            _reactivate_user(api, admin_token, viewer["id"])
            print("  Reactivated")
    else:
        viewer = _create_user(api, admin_token, args.viewer_email,
                              args.viewer_password, args.client_slug, "viewer")

    state["viewer_email"] = args.viewer_email
    state["viewer_password"] = args.viewer_password

    # --- MFA test account ---
    print(f"\n[4/4] Setting up MFA test account ({args.mfa_email})...")
    mfa_user = _find_user(users, args.mfa_email)

    if mfa_user and args.rebuild:
        print("  --rebuild: resetting MFA test account")
        _reset_password(api, admin_token, mfa_user["id"], args.mfa_password)
        _reactivate_user(api, admin_token, mfa_user["id"])
        # Disable MFA if it was previously enabled
        saved_secret = state.get("mfa_test_secret")
        if saved_secret:
            print("  Disabling existing MFA...")
            try:
                mfa_token = _login(api, args.mfa_email, args.mfa_password, saved_secret)
                _disable_mfa(api, mfa_token, saved_secret)
                print("  MFA disabled")
            except Exception as e:
                print(f"  Could not disable MFA ({e}) — will attempt fresh setup anyway")
        state.pop("mfa_test_secret", None)
        state.pop("mfa_enabled", None)
        mfa_user = _find_user(_get_users(api, admin_token), args.mfa_email)

    elif mfa_user:
        print("  Already exists")
        if not mfa_user["is_active"]:
            _reactivate_user(api, admin_token, mfa_user["id"])
            print("  Reactivated")
    else:
        mfa_user = _create_user(api, admin_token, args.mfa_email,
                                args.mfa_password, args.client_slug, "viewer")

    state["mfa_test_email"] = args.mfa_email
    state["mfa_test_password"] = args.mfa_password

    # Enable MFA on the test account (if not already done)
    if not state.get("mfa_enabled"):
        print("  Setting up TOTP MFA...")
        mfa_token = _login(api, args.mfa_email, args.mfa_password)
        secret = _setup_mfa(api, mfa_token)
        print(f"  Confirming with TOTP code...")
        _confirm_mfa(api, mfa_token, secret)
        state["mfa_test_secret"] = secret
        state["mfa_enabled"] = True
        print(f"  MFA enabled. Secret saved to state file.")
    else:
        print("  MFA already configured — skipping")

    state["client_slug"] = args.client_slug
    state["admin_email"] = args.admin_email
    state["admin_password"] = args.admin_password

    # Save state
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2))
    print(f"\n✓ State saved to {state_file}")
    print("\nReady to run:")
    print(f"  python scripts/capture_screenshots.py --base-url {args.base_url}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:5010",
                        help="Platform URL (default: http://localhost:5010)")
    parser.add_argument("--admin-email", default="admin@example.com")
    parser.add_argument("--admin-password", default="changeme123")
    parser.add_argument("--client-slug", default="acme-test",
                        help="Client slug to assign test accounts to (default: acme-test)")
    parser.add_argument("--viewer-email", default=DEFAULT_VIEWER_EMAIL)
    parser.add_argument("--viewer-password", default=DEFAULT_VIEWER_PASS)
    parser.add_argument("--mfa-email", default=DEFAULT_MFA_EMAIL)
    parser.add_argument("--mfa-password", default=DEFAULT_MFA_PASS)
    parser.add_argument("--rebuild", action="store_true",
                        help="Reset all test account state before setup")
    parser.add_argument("--state-file", default="scripts/.screenshot_state.json",
                        help="Path to save credentials and MFA secret")
    args = parser.parse_args()
    setup(args)


if __name__ == "__main__":
    main()