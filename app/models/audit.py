"""Audit log — append-only record of every staff/admin action."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, OptionalJsonB, UuidFk


class AuditLog(Base):
    """Append-only. App role gets only INSERT — no UPDATE/DELETE.

    Set up via migration::

        REVOKE UPDATE, DELETE ON audit_logs FROM app_role;

    The table is partitioned by month at scale (handled in a later migration).
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)

    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)  # staff|system|customer
    actor_id: Mapped[UuidFk | None] = mapped_column(nullable=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[UuidFk | None] = mapped_column(nullable=True)

    before: Mapped[OptionalJsonB]
    after: Mapped[OptionalJsonB]

    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[CreatedAt]
