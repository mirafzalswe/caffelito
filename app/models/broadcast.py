"""Owner-initiated broadcasts to all linked Telegram customers."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, OptionalDt, UuidFk, UuidPk


BROADCAST_STATUSES = ("draft", "sending", "done", "failed")
BROADCAST_MEDIA_TYPES = ("photo", "video")


class Broadcast(Base):
    __tablename__ = "broadcasts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','sending','done','failed')",
            name="status_valid",
        ),
        CheckConstraint(
            "media_type IS NULL OR media_type IN ('photo','video')",
            name="media_type_valid",
        ),
        Index("ix_broadcasts_tenant", "tenant_id", "created_at"),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    media_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'")
    )

    total_recipients: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    sent_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[CreatedAt]
    sent_at: Mapped[OptionalDt] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
