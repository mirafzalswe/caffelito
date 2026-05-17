"""Tenant — top-level isolation unit. One tenant = one coffee chain (or single shop)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, JsonB, UpdatedAt, UuidPk


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("plan IN ('starter','growth','chain')", name="plan_valid"),
        CheckConstraint(
            "status IN ('trial','active','suspended','churned')", name="status_valid"
        ),
    )

    id: Mapped[UuidPk]
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'starter'"))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'trial'")
    )
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    default_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'UTC'")
    )
    settings: Mapped[JsonB]

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
