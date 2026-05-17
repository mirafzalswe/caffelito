"""Manual bonus grants by admin/owner.

Three flavours:
* ``grant_free_coffee`` — adds N redeem-ready free coffees.
  Implementation: insert N ``loyalty_cards`` rows directly with
  ``status='complete'`` linked to a synthetic free-grant transaction.
* ``grant_cashback`` — credits the user's wallet.
* ``grant_stamps`` — bumps the active loyalty card by N stamps; rolls over
  to a fresh card on completion (same logic as ``record_purchase`` punchcard).

All three write to ``audit_logs`` and ``outbox_events`` so notifications
fire and the action is reviewable.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.config import settings
from app.domain import events
from app.domain import wallet as wallet_svc
from app.domain.audit import record_audit
from app.domain.errors import CampaignNotApplicable
from app.domain.outbox import enqueue_event
from app.models import (
    Campaign,
    LedgerEntry,
    LoyaltyCard,
    Transaction,
)


async def _pick_punchcard_campaign(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    campaign_id: uuid.UUID | None,
) -> Campaign | None:
    """Resolve which punchcard campaign a manual grant should attach to.

    If ``campaign_id`` is given, fetch that exact campaign (must be active and
    of type 'punchcard'). Otherwise return the highest-priority active one.
    """
    if campaign_id is not None:
        return (
            await session.execute(
                select(Campaign).where(
                    Campaign.id == campaign_id,
                    Campaign.tenant_id == tenant_id,
                    Campaign.type == "punchcard",
                    Campaign.status == "active",
                )
            )
        ).scalar_one_or_none()
    return (
        await session.execute(
            select(Campaign)
            .where(
                Campaign.tenant_id == tenant_id,
                Campaign.type == "punchcard",
                Campaign.status == "active",
            )
            .order_by(Campaign.priority.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Free coffee
# ---------------------------------------------------------------------------


async def grant_free_coffee(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    qty: int,
    reason: str,
    client_request_id: str,
    currency: str = "USD",
    campaign_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert N complete loyalty_cards so the user gains N free-coffees.

    If ``campaign_id`` is given, the free coffee is tied to that punchcard
    campaign. Otherwise the highest-priority active punchcard is used.
    """
    if qty <= 0:
        raise ValueError("qty must be positive")

    camp = await _pick_punchcard_campaign(
        session, tenant_id=tenant_id, campaign_id=campaign_id
    )
    if camp is None:
        raise CampaignNotApplicable(
            "Не найдена активная punchcard-кампания. Бесплатные кофе нельзя выдать без неё."
        )

    rules = camp.rules or {}
    stamps_required = int(rules.get("stamps_required", 10))
    expires_after_days = int(rules.get("expires_after_days") or settings.punchcard_default_expires_days)

    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="manual_grant",
        status="committed",
        total_amount=Decimal("0.00"),
        currency=currency,
        source="admin_panel",
        client_request_id=client_request_id,
        notes=f"manual grant: {qty} free coffee — {reason}",
        metadata_={"grant_kind": "free_coffee", "qty": qty},
    )
    session.add(tx)
    await session.flush()

    expires_at = now() + timedelta(days=expires_after_days)
    for _ in range(qty):
        card = LoyaltyCard(
            tenant_id=tenant_id,
            user_id=user_id,
            campaign_id=camp.id,
            stamps=stamps_required,
            stamps_required=stamps_required,
            status="complete",
            completed_at=now(),
            expires_at=expires_at,
        )
        session.add(card)
        await session.flush()
        session.add(
            LedgerEntry(
                tenant_id=tenant_id,
                user_id=user_id,
                transaction_id=tx.id,
                account=f"card:{camp.id}",
                delta=Decimal(stamps_required),
                unit="stamp",
                reason="manual_grant_free",
            )
        )
        await enqueue_event(
            session,
            tenant_id=tenant_id,
            aggregate_type=events.AGG_LOYALTY_CARD,
            aggregate_id=card.id,
            type_=events.EVT_FREE_UNLOCKED,
            payload={
                "user_id": str(user_id),
                "card_id": str(card.id),
                "campaign_id": str(camp.id),
                "manual": True,
            },
        )

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_type="staff",
        actor_id=staff_id,
        action="bonus.free_coffee",
        target_type="user",
        target_id=user_id,
        after={"qty": qty},
        reason=reason,
    )

    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=user_id)
    return tx.id


# ---------------------------------------------------------------------------
# Cashback
# ---------------------------------------------------------------------------


async def grant_cashback(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    reason: str,
    client_request_id: str,
    expires_after_days: int | None = None,
) -> uuid.UUID:
    if amount <= 0:
        raise ValueError("amount must be positive")

    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="manual_grant",
        status="committed",
        total_amount=Decimal("0.00"),
        currency=currency,
        source="admin_panel",
        client_request_id=client_request_id,
        notes=f"manual grant: cashback {amount} {currency} — {reason}",
        metadata_={"grant_kind": "cashback", "amount": str(amount)},
    )
    session.add(tx)
    await session.flush()

    await wallet_svc.credit(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        currency=currency,
        amount=amount,
        source_type="manual",
        source_id=tx.id,
        idempotency_key=f"manual_grant:{tx.id}",
        expires_after_days=expires_after_days,
    )

    session.add(
        LedgerEntry(
            tenant_id=tenant_id,
            user_id=user_id,
            transaction_id=tx.id,
            account="wallet:cashback",
            delta=amount,
            unit="currency",
            reason="manual_grant_cashback",
        )
    )

    await enqueue_event(
        session,
        tenant_id=tenant_id,
        aggregate_type=events.AGG_WALLET,
        aggregate_id=user_id,
        type_=events.EVT_CASHBACK_EARNED,
        payload={
            "user_id": str(user_id),
            "amount": str(amount),
            "currency": currency,
            "transaction_id": str(tx.id),
            "manual": True,
        },
    )

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_type="staff",
        actor_id=staff_id,
        action="bonus.cashback",
        target_type="user",
        target_id=user_id,
        after={"amount": str(amount), "currency": currency},
        reason=reason,
    )

    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=user_id)
    return tx.id


# ---------------------------------------------------------------------------
# Stamps
# ---------------------------------------------------------------------------


async def grant_stamps(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    qty: int,
    reason: str,
    client_request_id: str,
    currency: str = "USD",
    campaign_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Add N stamps to the user's active card; roll over on completion.

    If ``campaign_id`` is given, stamps go to that specific punchcard;
    otherwise the highest-priority active punchcard is used.
    """
    if qty <= 0:
        raise ValueError("qty must be positive")

    camp = await _pick_punchcard_campaign(
        session, tenant_id=tenant_id, campaign_id=campaign_id
    )
    if camp is None:
        raise CampaignNotApplicable("Нет активной punchcard-кампании")

    rules = camp.rules or {}
    stamps_required = int(rules.get("stamps_required", 10))
    expires_after_days = int(rules.get("expires_after_days") or settings.punchcard_default_expires_days)

    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="manual_grant",
        status="committed",
        total_amount=Decimal("0.00"),
        currency=currency,
        source="admin_panel",
        client_request_id=client_request_id,
        notes=f"manual grant: {qty} stamps — {reason}",
        metadata_={"grant_kind": "stamps", "qty": qty},
    )
    session.add(tx)
    await session.flush()

    units_left = qty
    while units_left > 0:
        # Find or create open card
        card = (
            await session.execute(
                select(LoyaltyCard)
                .where(
                    LoyaltyCard.user_id == user_id,
                    LoyaltyCard.campaign_id == camp.id,
                    LoyaltyCard.status == "open",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if card is None:
            card = LoyaltyCard(
                tenant_id=tenant_id,
                user_id=user_id,
                campaign_id=camp.id,
                stamps=0,
                stamps_required=stamps_required,
                status="open",
                expires_at=now() + timedelta(days=expires_after_days),
            )
            session.add(card)
            await session.flush()

        prev_stamps = card.stamps
        room = card.stamps_required - prev_stamps
        take = min(units_left, room)
        will_complete = (prev_stamps + take) >= card.stamps_required

        await session.execute(
            update(LoyaltyCard)
            .where(LoyaltyCard.id == card.id, LoyaltyCard.version == card.version)
            .values(
                stamps=LoyaltyCard.stamps + take,
                status="complete" if will_complete else "open",
                completed_at=now() if will_complete else None,
                version=LoyaltyCard.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        card.stamps = prev_stamps + take
        card.version += 1
        if will_complete:
            card.status = "complete"

        session.add(
            LedgerEntry(
                tenant_id=tenant_id,
                user_id=user_id,
                transaction_id=tx.id,
                account=f"card:{camp.id}",
                delta=Decimal(take),
                unit="stamp",
                reason="manual_grant_stamps",
            )
        )

        if will_complete:
            await enqueue_event(
                session,
                tenant_id=tenant_id,
                aggregate_type=events.AGG_LOYALTY_CARD,
                aggregate_id=card.id,
                type_=events.EVT_FREE_UNLOCKED,
                payload={
                    "user_id": str(user_id),
                    "card_id": str(card.id),
                    "campaign_id": str(camp.id),
                    "manual": True,
                },
            )

        units_left -= take

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_type="staff",
        actor_id=staff_id,
        action="bonus.stamps",
        target_type="user",
        target_id=user_id,
        after={"qty": qty},
        reason=reason,
    )

    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=user_id)
    return tx.id
