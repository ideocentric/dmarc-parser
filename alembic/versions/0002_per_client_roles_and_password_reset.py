"""Per-client roles and password reset

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add per-client role column — temporarily nullable for data migration
    op.add_column("user_clients", sa.Column("role", sa.String(16), nullable=True))

    # Set per-client role from current global role: admin→admin, anything else→viewer
    conn.execute(text("""
        UPDATE user_clients
        SET role = CASE
            WHEN (SELECT role FROM users WHERE id = user_clients.user_id) = 'admin' THEN 'admin'
            ELSE 'viewer'
        END
    """))

    # Now enforce NOT NULL with default
    op.alter_column("user_clients", "role", nullable=False, server_default="viewer")

    # Collapse global roles: admin and client both become 'user' (role detail is now per-client)
    conn.execute(text("UPDATE users SET role = 'user' WHERE role IN ('admin', 'client')"))

    # Add temporary-password flag
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Approximate reverse: promote per-client admins back to global admin
    conn.execute(text("""
        UPDATE users
        SET role = CASE
            WHEN EXISTS (
                SELECT 1 FROM user_clients
                WHERE user_id = users.id AND role = 'admin'
            ) THEN 'admin'
            ELSE 'client'
        END
        WHERE users.role = 'user'
    """))

    op.drop_column("users", "must_change_password")
    op.drop_column("user_clients", "role")