"""Transactions — the user-visible operation log: purchase, redeem, refund, etc."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    JsonB,
    Money,
    UuidFk,
    UuidPk,
)


TX_TYPES = (
    "purchase",
    "redeem_free",
    "prepaid_consume",
    "manual_grant",
    "manual_revoke",
    "refund",
)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # IDEMPOTENCY KEY — same client_request_id ⇒ no duplicate transaction.
        UniqueConstraint(
            "tenant_id", "client_request_id", name="uq_tx_idempotency"
        ),
        CheckConstraint(
            "type IN " + str(TX_TYPES).replace(",)", ")"), name="type_valid"
        ),
        CheckConstraint(
            "status IN ('pending','committed','reversed')", name="status_valid"
        ),
        Index("ix_tx_user_ts", "user_id", "created_at"),
        Index("ix_tx_branch_ts", "branch_id", "created_at"),
        Index("ix_tx_staff_ts", "staff_id", "created_at"),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)

    branch_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("branches.id"), nullable=False
    )
    user_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    staff_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("staff.id"), nullable=False
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'committed'")
    )

    total_amount: Mapped[Money] = mapped_column(server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)

    reverses: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    reversed_by: Mapped[UuidFk | None] = mapped_column(nullable=True)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[JsonB] = mapped_column("metadata")

    created_at: Mapped[CreatedAt]


class TransactionItem(Base):
    __tablename__ = "transaction_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint(
            "paid_with IN ('money','prepaid','free')", name="paid_with_valid"
        ),
    )

    id: Mapped[UuidPk]
    transaction_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("products.id"), nullable=True
    )

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Money]
    discount: Mapped[Money] = mapped_column(server_default=text("0"))

    paid_with: Mapped[str] = mapped_column(String(16), nullable=False)
    prepaid_package_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("prepaid_packages.id"), nullable=True
    )
    loyalty_card_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("loyalty_cards.id"), nullable=True
    )
