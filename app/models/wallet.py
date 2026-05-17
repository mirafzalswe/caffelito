"""Cashback wallet — balance is a projection of wallet_entries (event-sourced)."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    Money,
    OptionalDt,
    UuidFk,
    UuidPk,
)


class CashbackWallet(Base):
    __tablename__ = "cashback_wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_wallet_user_ccy"),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)
    user_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance: Mapped[Money] = mapped_column(server_default=text("0"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class WalletEntry(Base):
    """Append-only wallet ledger. Balance == sum(amount). FIFO spend by created_at."""

    __tablename__ = "wallet_entries"
    __table_args__ = (
        UniqueConstraint("wallet_id", "idempotency_key", name="uq_wallet_entry_idem"),
        CheckConstraint(
            "kind IN ('earn','spend','expire','adjust','refund')", name="kind_valid"
        ),
        Index("ix_wallet_entries_wallet_ts", "wallet_id", "created_at"),
        Index(
            "ix_wallet_entries_expiring",
            "expires_at",
            postgresql_where=text("kind = 'earn' AND expires_at IS NOT NULL"),
        ),
    )

    id: Mapped[UuidPk]
    wallet_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("cashback_wallets.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Money] = mapped_column(Numeric(12, 2), nullable=False)  # +earn / -spend
    # How much of this row has been consumed by later spend/expire entries.
    # Only meaningful for ``kind='earn'``; left at 0 for spend/expire rows.
    spent_amount: Mapped[Money] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[UuidFk | None] = mapped_column(nullable=True)
    expires_at: Mapped[OptionalDt]
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[CreatedAt]
