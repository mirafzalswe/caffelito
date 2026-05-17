"""Loyalty cards (punchcard state) and prepaid packages."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    JsonB,
    Money,
    OptionalDt,
    UuidFk,
    UuidPk,
)


# ---- Punchcard state ---------------------------------------------------------


class LoyaltyCard(Base):
    """One active loyalty card per (user, campaign).

    Lifecycle:
        open       — accumulating stamps
        complete   — stamps_required reached, free coffee waiting to redeem
        redeemed   — free coffee received; card is closed
        expired    — passed expires_at without redeem

    A new card is opened automatically when the previous one rolls over.
    """

    __tablename__ = "loyalty_cards"
    __table_args__ = (
        CheckConstraint("stamps >= 0", name="stamps_non_negative"),
        CheckConstraint(
            "status IN ('open','complete','redeemed','expired')",
            name="status_valid",
        ),
        # Only one active (open|complete) card per (user, campaign).
        Index(
            "uq_loyalty_active",
            "user_id",
            "campaign_id",
            unique=True,
            postgresql_where=text("status IN ('open','complete')"),
        ),
        Index("ix_loyalty_user", "user_id"),
        Index(
            "ix_loyalty_expiring",
            "expires_at",
            postgresql_where=text("status IN ('open','complete')"),
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)
    user_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )

    stamps: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    stamps_required: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'open'")
    )

    opened_at: Mapped[CreatedAt]
    completed_at: Mapped[OptionalDt]
    redeemed_at: Mapped[OptionalDt]
    expires_at: Mapped[OptionalDt]

    redeemed_tx_id: Mapped[UuidFk | None] = mapped_column(nullable=True)

    # Optimistic concurrency token. Bumped on every UPDATE.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


# ---- Prepaid packages --------------------------------------------------------


class PrepaidPackage(Base):
    """A prepaid package: customer paid upfront for N units of a product scope."""

    __tablename__ = "prepaid_packages"
    __table_args__ = (
        CheckConstraint("qty_total > 0", name="qty_total_positive"),
        CheckConstraint("qty_remaining >= 0", name="qty_remaining_non_negative"),
        CheckConstraint("qty_remaining <= qty_total", name="qty_remaining_le_total"),
        CheckConstraint(
            "status IN ('active','exhausted','refunded','expired','suspended')",
            name="status_valid",
        ),
        Index(
            "ix_prepaid_user_active",
            "user_id",
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_prepaid_expiring",
            "expires_at",
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)
    user_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("campaigns.id"), nullable=True
    )

    # Snapshot of which products this package can be spent on (frozen at opening time).
    product_scope: Mapped[JsonB]

    qty_total: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[Money]
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )

    opened_by: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
    opened_at: Mapped[CreatedAt]
    expires_at: Mapped[OptionalDt]
    closed_at: Mapped[OptionalDt]

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
