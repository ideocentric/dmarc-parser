"""Add per-client MFA enforcement flags

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("mfa_required_admins", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("clients", sa.Column("mfa_required_viewers", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("clients", "mfa_required_viewers")
    op.drop_column("clients", "mfa_required_admins")