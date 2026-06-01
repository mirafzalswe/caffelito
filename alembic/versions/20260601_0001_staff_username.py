"""staff username

Revision ID: c1a2b3d4e5f6
Revises: 61b99970ba02
Create Date: 2026-06-01 00:00:00.000000

Add a ``username`` login identifier to ``staff``:
- Case-insensitive (CITEXT), unique per tenant.
- Nullable so existing rows survive; backfilled from ``email`` where present
  so current owners keep logging in with the value they already use.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: str | Sequence[str] | None = "61b99970ba02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CITEXT extension is already installed by the initial migration (email).
    op.execute("ALTER TABLE staff ADD COLUMN username CITEXT")
    # Backfill from email so pre-existing owners keep their current login.
    op.execute("UPDATE staff SET username = email WHERE username IS NULL AND email IS NOT NULL")
    op.execute(
        "ALTER TABLE staff "
        "ADD CONSTRAINT uq_staff_tenant_username UNIQUE (tenant_id, username)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE staff DROP CONSTRAINT IF EXISTS uq_staff_tenant_username")
    op.execute("ALTER TABLE staff DROP COLUMN IF EXISTS username")
