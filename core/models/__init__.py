"""
Unified data models — single database, all tables in one place.
All DMARC data tables carry client_id for tenant scoping.
"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, JSON, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, PyEnum):
    super_admin = "super_admin"
    user = "user"


class ClientRole(str, PyEnum):
    admin = "admin"
    viewer = "viewer"


# ---------------------------------------------------------------------------
# Tenant / IAM tables
# ---------------------------------------------------------------------------

class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_required_admins: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_required_viewers: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domains: Mapped[list["Domain"]] = relationship("Domain", back_populates="client")
    user_clients: Mapped[list["UserClient"]] = relationship("UserClient", back_populates="client")
    imap_config: Mapped["ImapConfig | None"] = relationship("ImapConfig", back_populates="client", uselist=False)


class Domain(Base):
    __tablename__ = "domains"
    __table_args__ = (UniqueConstraint("client_id", "domain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped["Client"] = relationship("Client", back_populates="domains")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    # VARCHAR avoids PostgreSQL native ENUM — simpler to extend
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    azure_oid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_clients: Mapped[list["UserClient"]] = relationship("UserClient", back_populates="user")


class UserClient(Base):
    """Maps users to their permitted clients with a per-client role (admin|viewer)."""
    __tablename__ = "user_clients"
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")

    user: Mapped["User"] = relationship("User", back_populates="user_clients")
    client: Mapped["Client"] = relationship("Client", back_populates="user_clients")


class ImapConfig(Base):
    __tablename__ = "imap_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), unique=True, nullable=False)
    # 'imap' = standard IMAP with username/password
    # 'office365' = Microsoft 365 via OAuth2 client credentials
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="imap")
    host: Mapped[str] = mapped_column(String(253), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    inbox_folder: Mapped[str] = mapped_column(String(256), default="INBOX", nullable=False)
    processed_folder: Mapped[str | None] = mapped_column(String(256), nullable=True, default="DMARC-Processed")
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_poll_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_poll_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Office 365 OAuth2 fields (encrypted at rest)
    oauth2_tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    oauth2_client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    oauth2_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped["Client"] = relationship("Client", back_populates="imap_config")


# ---------------------------------------------------------------------------
# DMARC data tables — all scoped by client_id
# ---------------------------------------------------------------------------

class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("client_id", "report_id"),
        Index("ix_reports_client_date", "client_id", "begin_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("domains.id"), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    org_name: Mapped[str] = mapped_column(String(256), nullable=False)
    org_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    report_id: Mapped[str] = mapped_column(String(256), nullable=False)
    begin_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    policy_adkim: Mapped[str | None] = mapped_column(String(8), nullable=True)
    policy_aspf: Mapped[str | None] = mapped_column(String(8), nullable=True)
    policy_p: Mapped[str | None] = mapped_column(String(16), nullable=True)
    policy_sp: Mapped[str | None] = mapped_column(String(16), nullable=True)
    policy_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    records: Mapped[list["Record"]] = relationship("Record", back_populates="report")


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (
        Index("ix_records_client_ip", "client_id", "source_ip"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    source_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    dkim_result: Mapped[str] = mapped_column(String(16), nullable=False)
    spf_result: Mapped[str] = mapped_column(String(16), nullable=False)
    header_from: Mapped[str | None] = mapped_column(String(253), nullable=True)
    envelope_from: Mapped[str | None] = mapped_column(String(253), nullable=True)
    envelope_to: Mapped[str | None] = mapped_column(String(253), nullable=True)
    geo_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    geo_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    geo_subdivision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    geo_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    whois_org: Mapped[str | None] = mapped_column(String(256), nullable=True)
    whois_asn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    whois_as_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    report: Mapped["Report"] = relationship("Report", back_populates="records")
    auth_results: Mapped[list["AuthResult"]] = relationship("AuthResult", back_populates="record")
    flags: Mapped[list["Flag"]] = relationship("Flag", back_populates="record")


class AuthResult(Base):
    __tablename__ = "auth_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), nullable=False, index=True)
    auth_type: Mapped[str] = mapped_column(String(8), nullable=False)   # dkim | spf
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    selector: Mapped[str | None] = mapped_column(String(256), nullable=True)

    record: Mapped["Record"] = relationship("Record", back_populates="auth_results")


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        Index("ix_flags_client_open", "client_id", "acknowledged_at"),
        Index("ix_flags_client_type", "client_id", "flag_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), nullable=False, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    flag_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(256), nullable=True)

    record: Mapped["Record"] = relationship("Record", back_populates="flags")


class ProcessedFile(Base):
    __tablename__ = "processed_files"
    __table_args__ = (UniqueConstraint("client_id", "checksum"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IPWhoisCache(Base):
    """One row per unique IP — avoids repeated WHOIS lookups for the same address."""
    __tablename__ = "ip_whois_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ip: Mapped[str] = mapped_column(String(45), unique=True, nullable=False, index=True)
    org: Mapped[str | None] = mapped_column(String(256), nullable=True)
    asn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    as_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cidr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Issued refresh token JTIs — used for rotation and revocation."""
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthState(Base):
    """Short-lived OAuth2 state tokens — replaces in-memory dict for multi-worker safety."""
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())