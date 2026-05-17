"""Free coffee redemption — finalises an open ``loyalty_card.status='complete'``."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.domain import events
from app.domain.errors import (
    FreeCoffeeExpired,
    FreeCoffeeNotAvailable,
)
from app.domain.idempotency import find_replay
from app.domain.outbox import enqueue_event
from app.models import LedgerEntry, LoyaltyCard, Transaction, TransactionItem


async def redeem_free_coffee(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    product_id: uuid.UUID | None,
    client_request_id: str,
    currency: str = "USD",
    card_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Consume one free coffee. Returns the new transaction id.

    If ``card_id`` is given, redeems from that specific card (used when the
    customer has free coffees on multiple cards and the barista picked one).
    Otherwise picks the oldest ``status='complete'`` card for the user.
    Expired cards are skipped and marked ``expired``.
    """
    # Idempotency
    replay = await find_replay(
        session,
        tenant_id=tenant_id,
        client_request_id=client_request_id,
        expected_type="redeem_free",
    )
    if replay is not None:
        return replay.id

    base_stmt = select(LoyaltyCard).where(
        LoyaltyCard.tenant_id == tenant_id,
        LoyaltyCard.user_id == user_id,
        LoyaltyCard.status == "complete",
    )
    if card_id is not None:
        stmt = base_stmt.where(LoyaltyCard.id == card_id).with_for_update()
    else:
        stmt = (
            base_stmt
            .order_by(LoyaltyCard.completed_at.asc().nullslast())
            .with_for_update()
            .limit(1)
        )
    card = (await session.execute(stmt)).scalar_one_or_none()
    if card is None:
        raise FreeCoffeeNotAvailable

    if card.expires_at is not None and card.expires_at < now():
        await session.execute(
            update(LoyaltyCard)
            .where(LoyaltyCard.id == card.id)
            .values(status="expired", version=LoyaltyCard.version + 1)
        )
        raise FreeCoffeeExpired

    # Create the redemption transaction
    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="redeem_free",
        status="committed",
        total_amount=Decimal("0.00"),
        currency=currency,
        source="staff_bot",
        client_request_id=client_request_id,
    )
    session.add(tx)
    await session.flush()

    session.add(
        TransactionItem(
            transaction_id=tx.id,
            product_id=product_id,
            qty=1,
            unit_price=Decimal("0.00"),
            paid_with="free",
            loyalty_card_id=card.id,
        )
    )

    # Close the card
    await session.execute(
        update(LoyaltyCard)
        .where(LoyaltyCard.id == card.id, LoyaltyCard.version == card.version)
        .values(
            status="redeemed",
            redeemed_at=now(),
            redeemed_tx_id=tx.id,
            version=LoyaltyCard.version + 1,
        )
    )

    session.add(
        LedgerEntry(
            tenant_id=tenant_id,
            user_id=user_id,
            transaction_id=tx.id,
            account=f"card:{card.campaign_id}",
            delta=Decimal("-1"),
            unit="coffee_unit",
            reason="free_coffee_redeem",
        )
    )

    await enqueue_event(
        session,
        tenant_id=tenant_id,
        aggregate_type=events.AGG_LOYALTY_CARD,
        aggregate_id=card.id,
        type_=events.EVT_FREE_REDEEMED,
        payload={
            "user_id": str(user_id),
            "card_id": str(card.id),
            "transaction_id": str(tx.id),
        },
    )

    # Refresh dashboard projection
    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=user_id)

    return tx.id
