"""
Microsoft 365 OAuth2 token acquisition for IMAP access.

Uses the client credentials grant (app-only auth) with the
https://outlook.office365.com/.default scope, which is required for
IMAP.AccessAsApp application permissions.

Prerequisites (Azure portal):
  1. Register an app in Azure AD.
  2. Add API permission: Office 365 Exchange Online → IMAP.AccessAsApp (Application).
  3. Grant admin consent.
  4. In Exchange Online PowerShell:
       New-ServicePrincipalService -AppId <client_id> -ServiceId <object_id> -Organization <tenant>
       Add-MailboxPermission -Identity <shared@domain.com> -User <service_principal> -AccessRights FullAccess
"""
import logging
import time

log = logging.getLogger(__name__)

# Module-level token cache: (tenant_id, client_id) → (token, expires_at)
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}

SCOPE = ["https://outlook.office365.com/.default"]


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """
    Return a valid Bearer token, using the module-level cache to avoid
    re-fetching before expiry (tokens are valid for ~1 hour).
    """
    cache_key = (tenant_id, client_id)
    cached = _token_cache.get(cache_key)
    if cached:
        token, expires_at = cached
        # Refresh 5 minutes before expiry
        if time.time() < expires_at - 300:
            return token

    try:
        from msal import ConfidentialClientApplication
    except ImportError:
        raise RuntimeError("msal package is not installed — add msal to requirements.txt")

    app = ConfidentialClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )

    result = app.acquire_token_for_client(scopes=SCOPE)

    if "access_token" not in result:
        error = result.get("error", "unknown")
        description = result.get("error_description", "No description")
        raise RuntimeError(f"OAuth2 token request failed ({error}): {description}")

    token = result["access_token"]
    expires_in = result.get("expires_in", 3600)
    _token_cache[cache_key] = (token, time.time() + expires_in)

    log.debug("Acquired new Office 365 OAuth2 token for client_id=%s (expires_in=%ds)", client_id, expires_in)
    return token