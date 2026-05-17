"""Notification templates and outbound job queue."""

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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    JsonB,
    OptionalDt,
    OptionalJsonB,
    UuidFk,
    UuidPk,
)


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "code",
            "language",
            "variant",
            name="uq_notif_tpl_unique",
        ),
        CheckConstraint(
            "channel IN ('telegram','sms','push')", name="channel_valid"
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    buttons: Mapped[OptionalJsonB]
    variant: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'A'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','sent','failed','skipped','cancelled')",
            name="status_valid",
        ),
        Index(
            "ix_notif_due",
            "scheduled_at",
            postgresql_where=text("status = 'queued'"),
        ),
        Index("ix_notif_user", "user_id"),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk | None] = mapped_column(nullable=True)
    user_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[OptionalDt] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'queued'")
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    context: Mapped[JsonB]
    sent_at: Mapped[OptionalDt]
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Stable hash of the event payload — used by the partial unique index
    # ``uq_notif_dedup`` to make ``handle_event`` idempotent on outbox replay.
    dedup_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[CreatedAt]
