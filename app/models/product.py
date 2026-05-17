"""Product catalog. Loyalty engine references products by id/category/SKU."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, JsonB, Money, UuidFk, UuidPk


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        Index(
            "ix_products_tenant_active",
            "tenant_id",
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_price: Mapped[Money]

    is_loyalty_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    metadata_: Mapped[JsonB] = mapped_column("metadata")

    created_at: Mapped[CreatedAt]
