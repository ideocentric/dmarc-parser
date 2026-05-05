"""Add WHOIS enrichment fields to records and ip_whois_cache table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Denormalised fields on records — populated from the cache after lookup
    op.add_column("records", sa.Column("whois_org",     sa.String(256), nullable=True))
    op.add_column("records", sa.Column("whois_asn",     sa.String(16),  nullable=True))
    op.add_column("records", sa.Column("whois_as_name", sa.String(256), nullable=True))

    # One row per unique IP — avoids repeated lookups for the same address
    op.create_table(
        "ip_whois_cache",
        sa.Column("id",         sa.Integer, primary_key=True),
        sa.Column("source_ip",  sa.String(45), nullable=False, unique=True),
        sa.Column("org",        sa.String(256), nullable=True),
        sa.Column("asn",        sa.String(16),  nullable=True),
        sa.Column("as_name",    sa.String(256), nullable=True),
        sa.Column("cidr",       sa.String(64),  nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ip_whois_cache_source_ip", "ip_whois_cache", ["source_ip"])


def downgrade() -> None:
    op.drop_table("ip_whois_cache")
    op.drop_column("records", "whois_as_name")
    op.drop_column("records", "whois_asn")
    op.drop_column("records", "whois_org")