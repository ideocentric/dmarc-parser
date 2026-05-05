import re
from datetime import datetime
from pydantic import BaseModel, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_DOMAIN_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$"
)


class ClientCreate(BaseModel):
    slug: str
    name: str

    @field_validator("slug")
    @classmethod
    def slug_safe(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase alphanumeric with hyphens, 2–63 characters, "
                "starting with a letter or digit"
            )
        return v


class ClientUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class ClientMfaPolicyUpdate(BaseModel):
    mfa_required_admins: bool | None = None
    mfa_required_viewers: bool | None = None


class ClientPurgeRequest(BaseModel):
    confirm_slug: str


class ClientPurgeResponse(BaseModel):
    slug: str
    purged_at: str
    deleted: dict
    deactivated_users: list[str]
    filesystem_removed: list[str]


class ClientRead(BaseModel):
    id: int
    slug: str
    name: str
    is_active: bool
    mfa_required_admins: bool = False
    mfa_required_viewers: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainCreate(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def valid_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not _DOMAIN_RE.match(v):
            raise ValueError("Invalid domain name — must be a valid fully-qualified domain (e.g. example.com)")
        return v


class DomainRead(BaseModel):
    id: int
    client_id: int
    domain: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}