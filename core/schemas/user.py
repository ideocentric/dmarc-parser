from datetime import datetime
from pydantic import BaseModel, EmailStr
from core.models import UserRole, ClientRole


class ClientRoleEntry(BaseModel):
    slug: str
    role: ClientRole

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.user
    client_roles: list[ClientRoleEntry] = []


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    client_roles: list[ClientRoleEntry] | None = None


class PasswordReset(BaseModel):
    new_password: str
    temporary: bool = False


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class UserRead(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    must_change_password: bool = False
    has_password: bool = True   # False for SSO-only accounts with no local password
    mfa_enabled: bool = False
    mfa_setup_required: bool = False  # True when platform requires MFA and user has not enrolled
    mfa_required: bool = False        # True when the platform has MFA_REQUIRED=true in config
    created_at: datetime
    client_slugs: list[str] = []
    client_roles: list[ClientRoleEntry] = []

    model_config = {"from_attributes": True}


class UserMe(UserRead):
    pass