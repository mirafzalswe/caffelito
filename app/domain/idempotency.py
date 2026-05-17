"""Idempotency helper — replay detection via transactions.client_request_id."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction


async def find_replay(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    client_request_id: str,
    expected_type: str | None = None,
) -> Transaction | None:
    """Return the original transaction for this idempotency key, or None.

    ``expected_type`` scopes the replay check to a single operation kind
    (``purchase``, ``refund``, ``redeem_free``, ``prepaid_consume`` …) so a
    refund call cannot mistakenly resurrect an old purchase that happened
    to share the same ``client_request_id``.
    """
    stmt = select(Transaction).where(
        Transaction.tenant_id == tenant_id,
        Transaction.client_request_id == client_request_id,
    )
    if expected_type is not None:
        stmt = stmt.where(Transaction.type == expected_type)
    return (await session.execute(stmt)).scalar_one_or_none()
