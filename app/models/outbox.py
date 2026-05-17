"""Outbox table for the transactional outbox pattern.

A worker polls unpublished rows and forwards events to the message bus
(or directly fans out in-process for MVP).
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, JsonB, OptionalDt, UuidFk


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_unpub",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UuidFk] = mapped_column(nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UuidFk] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[JsonB]
    created_at: Mapped[CreatedAt]
    published_at: Mapped[OptionalDt]
