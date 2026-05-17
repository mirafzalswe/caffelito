"""Helpers to write outbox events inside the same DB transaction."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent


async def enqueue_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    type_: str,
    payload: dict[str, Any],
) -> None:
    """Add an outbox row. The publisher worker forwards it later.

    Note: do NOT commit here — the caller's surrounding transaction is what
    guarantees atomicity (event written iff business state changes).
    """
    session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            type=type_,
            payload=payload,
        )
    )
