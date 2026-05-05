from sqlalchemy.orm import Session
from core.config import settings
from core.models import User, Client


def mfa_required_for_user(user: User, db: Session) -> bool:
    """Return True if platform policy requires this user to have MFA enabled.

    Priority (first match wins):
      1. super_admin — always enforced, hardcoded
      2. MFA_REQUIRED env var — enforces for all users
      3. Per-client: if any client the user belongs to requires MFA for their role
    """
    if user.role == "super_admin":
        return True

    if settings.mfa_required:
        return True

    for uc in user.user_clients:
        client = db.get(Client, uc.client_id)
        if client is None:
            continue
        if uc.role == "admin" and client.mfa_required_admins:
            return True
        if uc.role == "viewer" and client.mfa_required_viewers:
            return True

    return False