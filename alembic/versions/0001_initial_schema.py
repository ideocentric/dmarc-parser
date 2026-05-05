"""Initial schema — unified single-database design

Revision ID: 0001
Revises:
Create Date: 2026-05-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "domains",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "domain"),
    )
    op.create_index("ix_domains_client_id", "domains", ["client_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=True),
        sa.Column("azure_oid", sa.String(128), nullable=True, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "user_clients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.UniqueConstraint("user_id", "client_id"),
    )
    op.create_index("ix_user_clients_user_id", "user_clients", ["user_id"])
    op.create_index("ix_user_clients_client_id", "user_clients", ["client_id"])

    op.create_table(
        "imap_configs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False, unique=True),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("port", sa.Integer, nullable=False, server_default="993"),
        sa.Column("username", sa.String(256), nullable=False),
        sa.Column("encrypted_password", sa.Text, nullable=False),
        sa.Column("use_ssl", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("inbox_folder", sa.String(256), nullable=False, server_default="INBOX"),
        sa.Column("processed_folder", sa.String(256), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer, nullable=False, server_default="15"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_status", sa.String(32), nullable=True),
        sa.Column("last_poll_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("domain_id", sa.Integer, sa.ForeignKey("domains.id"), nullable=True),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("org_name", sa.String(256), nullable=False),
        sa.Column("org_email", sa.String(256), nullable=True),
        sa.Column("report_id", sa.String(256), nullable=False),
        sa.Column("begin_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_domain", sa.String(253), nullable=True),
        sa.Column("policy_adkim", sa.String(8), nullable=True),
        sa.Column("policy_aspf", sa.String(8), nullable=True),
        sa.Column("policy_p", sa.String(16), nullable=True),
        sa.Column("policy_sp", sa.String(16), nullable=True),
        sa.Column("policy_pct", sa.Integer, nullable=True),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "report_id"),
    )
    op.create_index("ix_reports_client_id", "reports", ["client_id"])
    op.create_index("ix_reports_domain_id", "reports", ["domain_id"])
    op.create_index("ix_reports_domain", "reports", ["domain"])
    op.create_index("ix_reports_client_date", "reports", ["client_id", "begin_date"])

    op.create_table(
        "records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("source_ip", sa.String(45), nullable=False),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("disposition", sa.String(16), nullable=False),
        sa.Column("dkim_result", sa.String(16), nullable=False),
        sa.Column("spf_result", sa.String(16), nullable=False),
        sa.Column("header_from", sa.String(253), nullable=True),
        sa.Column("envelope_from", sa.String(253), nullable=True),
        sa.Column("envelope_to", sa.String(253), nullable=True),
        sa.Column("geo_country", sa.String(8), nullable=True),
        sa.Column("geo_city", sa.String(128), nullable=True),
        sa.Column("geo_subdivision", sa.String(128), nullable=True),
        sa.Column("geo_latitude", sa.Float, nullable=True),
        sa.Column("geo_longitude", sa.Float, nullable=True),
    )
    op.create_index("ix_records_report_id", "records", ["report_id"])
    op.create_index("ix_records_client_id", "records", ["client_id"])
    op.create_index("ix_records_client_ip", "records", ["client_id", "source_ip"])

    op.create_table(
        "auth_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("records.id"), nullable=False),
        sa.Column("auth_type", sa.String(8), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("selector", sa.String(256), nullable=True),
    )
    op.create_index("ix_auth_results_record_id", "auth_results", ["record_id"])

    op.create_table(
        "flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("records.id"), nullable=False),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("flag_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("detail", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(256), nullable=True),
    )
    op.create_index("ix_flags_record_id", "flags", ["record_id"])
    op.create_index("ix_flags_client_id", "flags", ["client_id"])
    op.create_index("ix_flags_client_open", "flags", ["client_id", "acknowledged_at"])
    op.create_index("ix_flags_client_type", "flags", ["client_id", "flag_type"])

    op.create_table(
        "processed_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("client_id", "checksum"),
    )
    op.create_index("ix_processed_files_client_id", "processed_files", ["client_id"])


def downgrade() -> None:
    op.drop_table("processed_files")
    op.drop_table("flags")
    op.drop_table("auth_results")
    op.drop_table("records")
    op.drop_table("reports")
    op.drop_table("imap_configs")
    op.drop_table("user_clients")
    op.drop_table("users")
    op.drop_table("domains")
    op.drop_table("clients")