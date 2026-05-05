from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import PyJWTError
from sqlalchemy.orm import Session

from api.auth.jwt import verify_access_token
from core.database import get_db
from core.models import User, Client, UserClient, UserRole, ClientRole

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (PyJWTError, KeyError, ValueError):
        raise exc

    user = db.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise exc
    return user


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user


def get_accessible_client(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    """Resolve slug → Client, enforcing that the user has any assignment to this client."""
    client = db.query(Client).filter_by(slug=slug, is_active=True).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if current_user.role == UserRole.super_admin:
        return client

    assigned_ids = {uc.client_id for uc in current_user.user_clients}
    if client.id not in assigned_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to this client is not permitted")

    return client


def require_client_admin(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Requires super_admin OR admin role for the specific client (identified by path slug)."""
    if current_user.role == UserRole.super_admin:
        return current_user

    client = db.query(Client).filter_by(slug=slug, is_active=True).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    uc = db.query(UserClient).filter_by(user_id=current_user.id, client_id=client.id).first()
    if not uc or uc.role != ClientRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client admin access required")

    return current_user


def get_user_client_role(user: User, client_id: int) -> ClientRole | None:
    """Return the per-client role for a user, or None if not assigned."""
    for uc in user.user_clients:
        if uc.client_id == client_id:
            return ClientRole(uc.role)
    return None