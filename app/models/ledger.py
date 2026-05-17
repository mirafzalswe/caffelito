"""Append-only ledger of every loyalty / wallet effect of every transaction.

This is the source of truth for audits and recomputation. ``ledger_entries`` is
written in the *same DB transaction* as ``transactions`` and the projection
updates — never as a separate step.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UuidFk, UuidPk


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_user", "user_id", "created_at"),
        Index("ix_ledger_account", "account", "created_at"),
        Index("ix_ledger_tx", "transaction_id"),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)
    user_id: Mapped[UuidFk] = mapped_column(nullable=False)
    transaction_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )

    # Logical account: 'wallet:cashback', 'card:<campaign_id>', 'prepaid:<package_id>'
    account: Mapped[str] = mapped_column(String(128), nullable=False)
    delta: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)  # 'currency'|'stamp'|'coffee_unit'
    reason: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[CreatedAt]
