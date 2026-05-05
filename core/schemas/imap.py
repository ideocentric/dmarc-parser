import ipaddress
import socket
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator, model_validator


def _reject_internal_host(host: str | None) -> str | None:
    """Raise if the host resolves to a private/loopback/link-local address."""
    if host is None:
        return None
    try:
        addr = ipaddress.ip_address(socket.gethostbyname(host))
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError(
                f"IMAP host {host!r} resolves to an internal address — "
                "only public hosts are permitted"
            )
    except socket.gaierror:
        pass  # unknown hostname — let the connection attempt fail naturally
    return host


class ImapConfigCreate(BaseModel):
    auth_type: Literal["imap", "office365"] = "imap"
    # Common fields
    username: str                              # mailbox address for both types
    inbox_folder: str = "INBOX"
    processed_folder: str | None = "DMARC-Processed"
    poll_interval_minutes: int = 15
    # Standard IMAP fields
    host: str | None = None
    port: int = 993
    password: str | None = None
    use_ssl: bool = True
    # Office 365 OAuth2 fields
    oauth2_tenant_id: str | None = None
    oauth2_client_id: str | None = None
    oauth2_client_secret: str | None = None   # plain text — encrypted before storage

    @field_validator("host")
    @classmethod
    def no_ssrf_host(cls, v: str | None) -> str | None:
        return _reject_internal_host(v)

    @field_validator("port")
    @classmethod
    def valid_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("port must be between 1 and 65535")
        return v

    @model_validator(mode="after")
    def check_required_fields(self) -> "ImapConfigCreate":
        if self.auth_type == "imap":
            if not self.host:
                raise ValueError("host is required for IMAP configuration")
            if not self.password:
                raise ValueError("password is required for IMAP configuration")
        elif self.auth_type == "office365":
            missing = [f for f in ("oauth2_tenant_id", "oauth2_client_id", "oauth2_client_secret")
                       if not getattr(self, f)]
            if missing:
                raise ValueError(f"Office 365 requires: {', '.join(missing)}")
        return self


class ImapConfigUpdate(BaseModel):
    # Common
    username: str | None = None
    inbox_folder: str | None = None
    processed_folder: str | None = None
    poll_interval_minutes: int | None = None
    is_active: bool | None = None
    # Standard IMAP
    host: str | None = None
    port: int | None = None
    password: str | None = None
    use_ssl: bool | None = None
    # Office 365 OAuth2
    oauth2_tenant_id: str | None = None
    oauth2_client_id: str | None = None
    oauth2_client_secret: str | None = None

    @field_validator("host")
    @classmethod
    def no_ssrf_host(cls, v: str | None) -> str | None:
        return _reject_internal_host(v)

    @field_validator("port")
    @classmethod
    def valid_port(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 65535):
            raise ValueError("port must be between 1 and 65535")
        return v


class ImapConfigRead(BaseModel):
    id: int
    client_id: int
    auth_type: str
    host: str
    port: int
    username: str
    use_ssl: bool
    inbox_folder: str
    processed_folder: str | None
    poll_interval_minutes: int
    is_active: bool
    last_polled_at: datetime | None
    last_poll_status: str | None
    last_poll_message: str | None
    # OAuth2 fields (IDs only — secret never returned)
    oauth2_tenant_id: str | None
    oauth2_client_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PollResult(BaseModel):
    status: str           # ok | error
    messages_scanned: int
    reports_ingested: int
    message: str