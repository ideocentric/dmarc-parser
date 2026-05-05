"""
Azure AD SSO via MSAL.

Flow:
  1. GET /auth/azure/login  → returns {auth_url, state}
     Frontend redirects the browser to auth_url.
  2. Azure redirects back to AZURE_REDIRECT_URI with ?code=...&state=...
     Frontend POSTs {code, state} to POST /auth/azure/callback
     Backend exchanges code, upserts user, returns JWT tokens.

State is stored in the database (not in-memory) so the server is safe
to run with multiple workers or replicas.
"""
import secrets
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from core.config import settings
from core.models import OAuthState

log = logging.getLogger(__name__)

SCOPES = ["User.Read"]
STATE_TTL_MINUTES = 10


def _get_msal_app():
    try:
        import msal
        return msal.ConfidentialClientApplication(
            client_id=settings.azure_client_id,
            client_credential=settings.azure_client_secret,
            authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
        )
    except ImportError:
        raise RuntimeError("msal package is required for Azure SSO")


def get_auth_url(db: Session) -> tuple[str, str]:
    """Generate OAuth state, persist it to DB, return (auth_url, state)."""
    # Purge expired states opportunistically
    db.query(OAuthState).filter(OAuthState.expires_at < datetime.now(timezone.utc)).delete()

    state = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)
    db.add(OAuthState(state=state, expires_at=expires_at))
    db.commit()

    app = _get_msal_app()
    url = app.get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=settings.azure_redirect_uri,
    )
    return url, state


def exchange_code(code: str, state: str, db: Session) -> dict:
    """
    Validate state against DB, exchange auth code for tokens.
    Returns a dict with keys: oid, email, name.
    Raises ValueError on invalid/expired state or failed token exchange.
    """
    stored = db.query(OAuthState).filter_by(state=state).first()
    if not stored:
        raise ValueError("Invalid or expired OAuth state")
    if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        db.delete(stored)
        db.commit()
        raise ValueError("OAuth state has expired — please try signing in again")
    db.delete(stored)
    db.commit()

    app = _get_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=settings.azure_redirect_uri,
    )

    if "error" in result:
        raise ValueError(f"Azure token exchange failed: {result.get('error_description', result['error'])}")

    claims = result.get("id_token_claims", {})
    oid = claims.get("oid")
    email = claims.get("preferred_username") or claims.get("email") or claims.get("upn")
    name = claims.get("name", "")

    if not oid or not email:
        raise ValueError("Azure token missing required claims (oid, email)")

    return {"oid": oid, "email": email, "name": name}