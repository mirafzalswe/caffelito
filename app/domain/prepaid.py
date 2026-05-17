"""Prepaid package: open (sell N units) and consume (decrement on each visit)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.config import settings
from app.domain import events
from app.domain.errors import PrepaidExhausted, PrepaidNotFound
from app.domain.idempotency import find_replay
from app.domain.outbox import enqueue_event
from app.models import (
    LedgerEntry,
    PrepaidPackage,
    Transaction,
    TransactionItem,
)


# ---------------------------------------------------------------------------
# Open
# ---------------------------------------------------------------------------


async def open_package(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    qty: int,
    amount_paid: Decimal,
    currency: str,
    product_scope: dict[str, Any],
    client_request_id: str,
    expires_after_days: int | None = None,
    campaign_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Open a new package and record the purchase transaction.

    Returns ``(transaction_id, package_id)``.
    """
    if qty <= 0:
        raise ValueError("qty must be positive")
    if amount_paid < 0:
        raise ValueError("amount_paid must be non-negative")

    replay = await find_replay(
        session,
        tenant_id=tenant_id,
        client_request_id=client_request_id,
        expected_type="purchase",
    )
    if replay is not None:
        # On replay, locate the package opened by this transaction.
        stmt = select(PrepaidPackage).where(
            PrepaidPackage.opened_by == staff_id,
            PrepaidPackage.user_id == user_id,
            PrepaidPackage.opened_at >= replay.created_at,
        ).order_by(PrepaidPackage.opened_at.asc()).limit(1)
        pkg = (await session.execute(stmt)).scalar_one_or_none()
        return replay.id, (pkg.id if pkg else uuid.uuid4())

    expires_at = None
    days = expires_after_days or settings.prepaid_default_expires_days
    if days:
        expires_at = now() + timedelta(days=int(days))

    pkg = PrepaidPackage(
        tenant_id=tenant_id,
        user_id=user_id,
        campaign_id=campaign_id,
        product_scope=product_scope,
        qty_total=qty,
        qty_remaining=qty,
        amount_paid=amount_paid,
        currency=currency,
        status="active",
        opened_by=staff_id,
        expires_at=expires_at,
    )
    session.add(pkg)
    await session.flush()

    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="purchase",
        status="committed",
        total_amount=amount_paid,
        currency=currency,
        source="staff_bot",
        client_request_id=client_request_id,
        notes="prepaid package opened",
        metadata_={"prepaid_package_id": str(pkg.id), "qty": qty},
    )
    session.add(tx)
    await session.flush()

    session.add(
        LedgerEntry(
            tenant_id=tenant_id,
            user_id=user_id,
            transaction_id=tx.id,
            account=f"prepaid:{pkg.id}",
            delta=Decimal(qty),
            unit="coffee_unit",
            reason="prepaid_open",
        )
    )

    await enqueue_event(
        session,
        tenant_id=tenant_id,
        aggregate_type=events.AGG_PREPAID,
        aggregate_id=pkg.id,
        type_=events.EVT_PREPAID_OPENED,
        payload={
            "user_id": str(user_id),
            "package_id": str(pkg.id),
            "qty": qty,
            "amount_paid": str(amount_paid),
            "currency": currency,
        },
    )

    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=user_id)
    return tx.id, pkg.id


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------


async def consume_one(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    product_id: uuid.UUID | None,
    client_request_id: str,
    currency: str = "USD",
    package_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Consume one unit from a user's active prepaid package.

    If ``package_id`` is given, debit that specific package (used when the
    customer has more than one active package and the barista picked one).
    Otherwise pick the oldest-expiring active package (FIFO by expiration).

    Returns ``(transaction_id, package_id)``. Race-safe via conditional UPDATE
    (``WHERE qty_remaining > 0``) — concurrent consumes never go negative.
    """
    replay = await find_replay(
        session,
        tenant_id=tenant_id,
        client_request_id=client_request_id,
        expected_type="prepaid_consume",
    )
    if replay is not None:
        return replay.id, uuid.uuid4()

    base_stmt = select(PrepaidPackage).where(
        PrepaidPackage.tenant_id == tenant_id,
        PrepaidPackage.user_id == user_id,
        PrepaidPackage.status == "active",
        PrepaidPackage.qty_remaining > 0,
    )
    if package_id is not None:
        stmt = base_stmt.where(PrepaidPackage.id == package_id).with_for_update()
    else:
        stmt = (
            base_stmt
            .order_by(PrepaidPackage.expires_at.asc().nullslast())
            .with_for_update()
            .limit(1)
        )
    pkg = (await session.execute(stmt)).scalar_one_or_none()
    if pkg is None:
        raise PrepaidNotFound

    # Conditional decrement
    upd = (
        update(PrepaidPackage)
        .where(
            PrepaidPackage.id == pkg.id,
            PrepaidPackage.qty_remaining > 0,
            PrepaidPackage.version == pkg.version,
        )
        .values(
            qty_remaining=PrepaidPackage.qty_remaining - 1,
            version=PrepaidPackage.version + 1,
        )
    )
    res = await session.execute(upd)
    if res.rowcount != 1:
        raise PrepaidExhausted

    new_remaining = pkg.qty_remaining - 1

    # If now zero — close as exhausted
    if new_remaining == 0:
        await session.execute(
            update(PrepaidPackage)
            .where(PrepaidPackage.id == pkg.id)
            .values(status="exhausted", closed_at=now(), version=PrepaidPackage.version + 2)
        )

    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="prepaid_consume",
        status="committed",
        total_amount=Decimal("0.00"),
        currency=currency,
        source="staff_bot",
        client_request_id=client_request_id,
        metadata_={"prepaid_package_id": str(pkg.id)},
    )
    session.add(tx)
    await session.flush()

    session.add(
        TransactionItem(
            transaction_id=tx.id,
            product_id=product_id,
            qty=1,
            unit_price=Decimal("0.00"),
            paid_with="prepaid",
            prepaid_package_id=pkg.id,
        )
    )

    session.add(
        LedgerEntry(
            tenant_id=tenant_id,
            user_id=user_id,
            transaction_id=tx.id,
            account=f"prepaid:{pkg.id}",
            delta=Decimal("-1"),
            unit="coffee_unit",
            reason="prepaid_consume",
        )
    )

    await enqueue_event(
        session,
        tenant_id=tenant_id,
        aggregate_type=events.AGG_PREPAID,
        aggregate_id=pkg.id,
        type_=events.EVT_PREPAID_CONSUMED,
        payload={
            "user_id": str(user_id),
            "package_id": str(pkg.id),
            "remaining": new_remaining,
            "transaction_id": str(tx.id),
        },
    )
    if new_remaining == 0:
        await enqueue_event(
            session,
            tenant_id=tenant_id,
            aggregate_type=events.AGG_PREPAID,
            aggregate_id=pkg.id,
            type_=events.EVT_PREPAID_EXHAUSTED,
            payload={"user_id": str(user_id), "package_id": str(pkg.id)},
        )

    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=user_id)
    return tx.id, pkg.id
