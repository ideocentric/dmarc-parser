"""Add Office 365 OAuth2 fields to imap_configs

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("imap_configs", sa.Column(
        "auth_type", sa.String(16), nullable=False, server_default="imap"
    ))
    op.add_column("imap_configs", sa.Column("oauth2_tenant_id", sa.String(128), nullable=True))
    op.add_column("imap_configs", sa.Column("oauth2_client_id", sa.String(128), nullable=True))
    op.add_column("imap_configs", sa.Column("oauth2_client_secret", sa.Text, nullable=True))
    # encrypted_password must be nullable for Office 365 configs (no password used)
    op.alter_column("imap_configs", "encrypted_password", nullable=True)


def downgrade() -> None:
    op.alter_column("imap_configs", "encrypted_password", nullable=False)
    op.drop_column("imap_configs", "oauth2_client_secret")
    op.drop_column("imap_configs", "oauth2_client_id")
    op.drop_column("imap_configs", "oauth2_tenant_id")
    op.drop_column("imap_configs", "auth_type")