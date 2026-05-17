"""wallet_entries.spent_amount + FIFO debit/expire correctness

Cashback ledger has two kinds of writes that need to interact:

* ``earn`` rows grant balance with an optional ``expires_at``.
* ``spend`` / ``expire`` rows burn balance.

The MVP code that existed before this migration only decremented the
aggregate ``cashback_wallets.balance``; on expiration it burned the
whole earn row even when a portion had already been spent — which would
drive the projection negative.

We fix this by recording how much of each earn row has been consumed
on the row itself:

    wallet_entries.spent_amount NUMERIC(12,2) NOT NULL DEFAULT 0

``app.domain.wallet.debit`` allocates the spend FIFO across the user's
non-exhausted, non-expired earn rows and bumps ``spent_amount``. The
expiration cron burns ``amount - spent_amount`` (i.e. the still-unspent
remainder) and sets ``spent_amount = amount`` so subsequent runs are
no-ops.

Revision ID: 0006_wallet_fifo_tracking
Revises: 0005_app_role
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_wallet_fifo_tracking"
down_revision: str | Sequence[str] | None = "0005_app_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_entries
        ADD COLUMN IF NOT EXISTS spent_amount NUMERIC(12,2) NOT NULL DEFAULT 0
        """
    )
    # Helps the FIFO debit query: oldest available earn first.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_wallet_entries_earn_available
            ON wallet_entries (wallet_id, created_at)
            WHERE kind = 'earn' AND amount > spent_amount
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = 'spent_within_amount'
            ) THEN
                ALTER TABLE wallet_entries
                ADD CONSTRAINT spent_within_amount
                    CHECK (kind <> 'earn' OR spent_amount <= amount);
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE wallet_entries DROP CONSTRAINT IF EXISTS spent_within_amount"
    )
    op.execute("DROP INDEX IF EXISTS ix_wallet_entries_earn_available")
    op.execute("ALTER TABLE wallet_entries DROP COLUMN IF EXISTS spent_amount")
