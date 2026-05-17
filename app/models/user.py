"""User — end customer of a coffee shop. Identity by phone, not by Telegram ID."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    OptionalDt,
    PhoneE164,
    TgId,
    UpdatedAt,
    UuidFk,
    UuidPk,
)


class User(Base):
    """End-customer.

    A user can exist without ``telegram_id`` (created by admin from a phone
    number) — Telegram is linked deferred when the customer first hits
    /start and shares contact. Phone is unique per tenant.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','blocked','merged')", name="status_valid"
        ),
        # Active phones unique per tenant (allow merged/deleted duplicates)
        Index(
            "uq_users_tenant_phone",
            "tenant_id",
            "phone_e164",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Active telegram IDs unique per tenant
        Index(
            "uq_users_tenant_telegram",
            "tenant_id",
            "telegram_id",
            unique=True,
            postgresql_where=text("telegram_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        # Trigram index for fuzzy phone search by barista (last 4 digits, etc.)
        Index(
            "ix_users_phone_trgm",
            "phone_e164",
            postgresql_using="gin",
            postgresql_ops={"phone_e164": "gin_trgm_ops"},
        ),
        # Active opted-in users for notification fan-out
        Index(
            "ix_users_active_notify",
            "tenant_id",
            postgresql_where=text(
                "deleted_at IS NULL AND notify_opt_in = true AND telegram_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    phone_e164: Mapped[PhoneE164]
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telegram_id: Mapped[TgId]
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    language: Mapped[str] = mapped_column(
        String(2), nullable=False, server_default=text("'ru'")
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    notify_opt_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    notify_quiet_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    notify_quiet_to: Mapped[time | None] = mapped_column(Time, nullable=True)

    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_seen_at: Mapped[OptionalDt]
    last_seen_at: Mapped[OptionalDt]

    merged_into_user_id: Mapped[UuidFk | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
    deleted_at: Mapped[OptionalDt]


class UserDashboard(Base):
    """Read-model projection used by the customer bot to render the home screen.

    Updated by event handlers as a side effect of ledger writes. Reading this
    table is O(1) per request; we never compute aggregates from `transactions`
    on the bot path.
    """

    __tablename__ = "user_dashboard"

    user_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)

    stamps_total: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    stamps_required: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    free_coffees_available: Mapped[int] = mapped_column(
        nullable=False, server_default=text("0")
    )
    cashback_balance: Mapped[float] = mapped_column(  # numeric in DB; ORM as float for read-only
        nullable=False, server_default=text("0")
    )
    prepaid_remaining: Mapped[int] = mapped_column(
        nullable=False, server_default=text("0")
    )

    last_visit_at: Mapped[OptionalDt]
    last_visit_branch_id: Mapped[UuidFk | None] = mapped_column(nullable=True)
    visits_30d: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    rfm_segment: Mapped[str | None] = mapped_column(String(8), nullable=True)

    updated_at: Mapped[UpdatedAt]
