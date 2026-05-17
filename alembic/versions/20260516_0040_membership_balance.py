"""membership balance

Revision ID: 61b99970ba02
Revises: b69db76aae66
Create Date: 2026-05-16 00:40:51.540487

Switch memberships from "ticket" to "deposit" model:
- ``balance_remaining`` — what's left to spend; decreases on every purchase.
- ``expires_at`` becomes nullable — by default VIP lives until the balance
  is drained.
- New ``exhausted`` status for memberships whose balance reached zero.

Constraints are dropped/recreated via raw SQL with their literal names to
sidestep Alembic's NAMING_CONVENTION re-mangling.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '61b99970ba02'
down_revision: str | Sequence[str] | None = 'b69db76aae66'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add balance_remaining; backfill = amount_paid for existing rows.
    op.add_column(
        'memberships',
        sa.Column('balance_remaining', sa.Numeric(12, 2), nullable=True),
    )
    op.execute(
        "UPDATE memberships SET balance_remaining = amount_paid "
        "WHERE balance_remaining IS NULL"
    )
    op.alter_column('memberships', 'balance_remaining', nullable=False)

    # Allow expires_at to be NULL (open-ended VIP).
    op.alter_column('memberships', 'expires_at', nullable=True)

    # Replace status check to allow 'exhausted'.
    op.execute(
        "ALTER TABLE memberships "
        "DROP CONSTRAINT IF EXISTS ck_memberships_status_valid"
    )
    op.execute(
        "ALTER TABLE memberships "
        "ADD CONSTRAINT ck_memberships_status_valid "
        "CHECK (status IN ('active','expired','exhausted','cancelled'))"
    )

    # balance_remaining can't go negative.
    op.execute(
        "ALTER TABLE memberships "
        "ADD CONSTRAINT ck_memberships_balance_nonneg "
        "CHECK (balance_remaining >= 0)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE memberships "
        "DROP CONSTRAINT IF EXISTS ck_memberships_balance_nonneg"
    )
    op.execute(
        "ALTER TABLE memberships "
        "DROP CONSTRAINT IF EXISTS ck_memberships_status_valid"
    )
    op.execute(
        "ALTER TABLE memberships "
        "ADD CONSTRAINT ck_memberships_status_valid "
        "CHECK (status IN ('active','expired','cancelled'))"
    )
    op.alter_column('memberships', 'expires_at', nullable=False)
    op.drop_column('memberships', 'balance_remaining')
