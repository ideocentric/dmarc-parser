"""Add MFA fields to users table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.Text, nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean, nullable=False,
                                     server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")