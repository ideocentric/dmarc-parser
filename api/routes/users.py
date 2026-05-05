import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from api.deps import get_current_user, get_db, require_super_admin, get_user_client_role
from core.models import User, UserClient, Client, UserRole, ClientRole
from core.schemas.user import (
    ClientRoleEntry, UserCreate, UserUpdate, UserRead,
    PasswordReset, PasswordChange,
)
from core.security import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


def _to_read(user: User, visible_client_ids: set[int] | None = None) -> UserRead:
    """
    Build a UserRead for the given user.
    visible_client_ids: when set, client_roles is filtered to only include
    clients in that set — prevents non-super-admins from learning which other
    clients a user belongs to.
    """
    client_roles = [
        ClientRoleEntry(slug=uc.client.slug, role=uc.role)
        for uc in user.user_clients
        if visible_client_ids is None or uc.client_id in visible_client_ids
    ]
    return UserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        has_password=user.password_hash is not None,
        created_at=user.created_at,
        client_slugs=[cr.slug for cr in client_roles],
        client_roles=client_roles,
    )


def _is_admin_for_client(user: User, client_id: int) -> bool:
    role = get_user_client_role(user, client_id)
    return role == ClientRole.admin


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.super_admin:
        return [_to_read(u) for u in db.query(User).all()]
    # Client admins see users assigned to their admin clients
    admin_client_ids = {
        uc.client_id for uc in current_user.user_clients if uc.role == ClientRole.admin
    }
    if not admin_client_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    user_ids = {
        uc.user_id
        for uc in db.query(UserClient).filter(UserClient.client_id.in_(admin_client_ids)).all()
    }
    return [
        _to_read(u, visible_client_ids=admin_client_ids)
        for u in db.query(User).filter(User.id.in_(user_ids)).all()
    ]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only super_admin can create super_admin users
    if body.role == UserRole.super_admin and current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can create super admin users")

    # Non-super-admins must be a client admin
    if current_user.role != UserRole.super_admin:
        admin_client_ids = {
            uc.client_id for uc in current_user.user_clients if uc.role == ClientRole.admin
        }
        if not admin_client_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
        # Ensure all target clients are ones this admin manages
        for entry in body.client_roles:
            client = db.query(Client).filter_by(slug=entry.slug).first()
            if not client or client.id not in admin_client_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You do not have admin access to client '{entry.slug}'",
                )

    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=body.email, role=body.role.value, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()

    for entry in body.client_roles:
        client = db.query(Client).filter_by(slug=entry.slug).first()
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client '{entry.slug}' not found")
        db.add(UserClient(user_id=user.id, client_id=client.id, role=entry.role.value))

    db.commit()
    db.refresh(user)
    return _to_read(user)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.id != user_id and current_user.role != UserRole.super_admin:
        # Client admins can view users in their clients
        target = db.query(User).filter_by(id=user_id).first()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        target_client_ids = {uc.client_id for uc in target.user_clients}
        admin_client_ids = {
            uc.client_id for uc in current_user.user_clients if uc.role == ClientRole.admin
        }
        if not target_client_ids & admin_client_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return _to_read(target, visible_client_ids=admin_client_ids)

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # super_admin or own profile — full visibility
    visible = None if current_user.role == UserRole.super_admin else {
        uc.client_id for uc in current_user.user_clients
    }
    return _to_read(user, visible_client_ids=visible)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Only super_admin can change roles or edit arbitrary users
    if current_user.role != UserRole.super_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.email is not None and body.email != user.email:
        log.warning("Email change: user %d %r → %r (by user %d)", user.id, user.email, body.email, current_user.id)
        user.email = body.email
    if body.role is not None:
        if current_user.role != UserRole.super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can change global roles")
        user.role = body.role.value
    if body.is_active is not None:
        if current_user.role != UserRole.super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can change active status")
        user.is_active = body.is_active

    if body.client_roles is not None:
        if current_user.role != UserRole.super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can change client assignments")
        db.query(UserClient).filter_by(user_id=user.id).delete()
        for entry in body.client_roles:
            client = db.query(Client).filter_by(slug=entry.slug).first()
            if not client:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client '{entry.slug}' not found")
            db.add(UserClient(user_id=user.id, client_id=client.id, role=entry.role.value))

    db.commit()
    db.refresh(user)
    return _to_read(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int,
    body: PasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(User).filter_by(id=user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use change-password to update your own password",
        )
    elif current_user.role == UserRole.super_admin:
        pass  # full access to reset any other user
    else:
        # Client admin can reset passwords for users in their clients
        target_client_ids = {uc.client_id for uc in target.user_clients}
        admin_client_ids = {
            uc.client_id for uc in current_user.user_clients if uc.role == ClientRole.admin
        }
        if not target_client_ids & admin_client_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target.password_hash = hash_password(body.new_password)
    target.must_change_password = body.temporary
    db.commit()


@router.post("/{user_id}/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    user_id: int,
    body: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only change your own password")

    if not current_user.password_hash or not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
    db.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    db.commit()


@router.post("/{user_id}/reset-mfa", status_code=status.HTTP_204_NO_CONTENT)
def reset_mfa(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    """Clear a user's MFA enrolment. Super admin only. Used for lost-device recovery.
    The user will be forced to re-enrol on next login if MFA_REQUIRED is set."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /auth/mfa/disable to manage your own MFA",
        )
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled for this user")
    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    log.warning("MFA reset for user %d (%s) by super_admin %d (%s)",
                user.id, user.email, current_user.id, current_user.email)