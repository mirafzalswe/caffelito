"""VIP / tier memberships — one-shot payment for a time-bound discount.

Business rules:
- A customer can have at most ONE active membership at a time.
- While the membership is active (now < expires_at), purchases get
  ``discount_percent`` off and earn NO stamps and NO cashback.
- Money paid for the membership is not refundable — it's a "ticket".
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Money, OptionalDt, UuidFk, UuidPk


MEMBERSHIP_STATUSES = ("active", "expired", "exhausted", "cancelled")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','expired','exhausted','cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "discount_percent BETWEEN 1 AND 100",
            name="discount_valid",
        ),
        CheckConstraint("balance_remaining >= 0", name="balance_nonneg"),
        # Only one active row per user — enforced via a partial unique index.
        Index(
            "uq_membership_active",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_membership_expiry", "expires_at",
              postgresql_where=text("status = 'active'")),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk]
    user_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )

    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[Money]
    # Live deposit balance — drained on each purchase by (unit_price * qty)
    # after the % discount is applied.
    balance_remaining: Mapped[Money]

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )

    started_at: Mapped[CreatedAt]
    # Open-ended by default — VIP lives until ``balance_remaining`` hits zero.
    expires_at: Mapped[OptionalDt]
    cancelled_at: Mapped[OptionalDt]

    activated_by: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
