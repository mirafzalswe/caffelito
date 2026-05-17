"""Campaigns (loyalty rules). One configurable engine for all promo types."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, JsonB, OptionalDt, UpdatedAt, UuidFk, UuidPk


CAMPAIGN_TYPES = (
    "punchcard",
    "prepaid",
    "cashback",
    "bonus_item",
    "tiered_status",
    "first_purchase",
    "birthday",
)


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_campaigns_tenant_code"),
        CheckConstraint(
            "type IN " + str(CAMPAIGN_TYPES).replace(",)", ")"), name="type_valid"
        ),
        CheckConstraint(
            "status IN ('draft','active','paused','archived')",
            name="status_valid",
        ),
        Index(
            "ix_campaigns_active",
            "tenant_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'")
    )

    starts_at: Mapped[OptionalDt] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    ends_at: Mapped[OptionalDt]
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    stackable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # Rule definition — see IMPLEMENTATION_PLAN.md §3.6 for the JSON schema.
    rules: Mapped[JsonB]

    created_by: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class CampaignBranch(Base):
    __tablename__ = "campaign_branches"

    campaign_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True
    )


class CampaignProduct(Base):
    __tablename__ = "campaign_products"

    campaign_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
