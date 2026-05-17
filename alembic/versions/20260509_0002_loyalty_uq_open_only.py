"""relax loyalty active-card uniqueness to status='open' only

Why: the punchcard engine rolls a card over once it completes — it must be
allowed to open a fresh 'open' card while the prior card sits in
status='complete' awaiting redemption. The original index forbade this.

Revision ID: 0002_loyalty_uq_open_only
Revises: 0001_initial_schema
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_loyalty_uq_open_only"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_loyalty_active")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_loyalty_active
            ON loyalty_cards (user_id, campaign_id)
            WHERE status = 'open'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_loyalty_active")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_loyalty_active
            ON loyalty_cards (user_id, campaign_id)
            WHERE status IN ('open','complete')
        """
    )
