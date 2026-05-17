"""Branch — a physical coffee shop location belonging to a tenant."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, OptionalJsonB, UuidFk, UuidPk


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_branches_tenant_name"),
        CheckConstraint(
            "status IN ('active','closed','paused')", name="status_valid"
        ),
        Index(
            "ix_branches_tenant_active",
            "tenant_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    opening_hours: Mapped[OptionalJsonB]
    # Geo stored as separate lat/lng for portability (POINT requires PostGIS for proper indexing)
    geo_lat: Mapped[float | None] = mapped_column(nullable=True)
    geo_lng: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[CreatedAt]
