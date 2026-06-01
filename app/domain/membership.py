"""VIP / tier memberships — deposit model.

Business model:

- Customer pays an upfront amount (e.g. 300 000 UZS).
- The whole amount lands on ``balance_remaining``.
- Every paid line at purchase time costs ``unit_price * (1 - discount/100)``
  and is deducted from ``balance_remaining``.
- If a purchase would push the balance below zero, the purchase is refused
  with a ``DomainError`` (admin must split the order or sell a top-up).
- When the balance hits zero, the membership flips to ``exhausted``.
- One active membership per user — enforced by ``uq_membership_active``.
- Stamps and cashback are NOT awarded while a VIP membership is active.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.domain.errors import CampaignNotApplicable, DomainError
from app.models import Campaign, Membership, Transaction


async def get_active_membership(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    """Return the user's live VIP membership in this tenant, if any.

    Lazily transitions stale rows:
    - ``balance_remaining == 0`` → ``exhausted``
    - past ``expires_at`` (if set) → ``expired``
    """
    stmt = select(Membership).where(
        Membership.tenant_id == tenant_id,
        Membership.user_id == user_id,
        Membership.status == "active",
    )
    m = (await session.execute(stmt)).scalar_one_or_none()
    if m is None:
        return None
    if m.balance_remaining is not None and Decimal(m.balance_remaining) <= 0:
        await session.execute(
            update(Membership).where(Membership.id == m.id).values(status="exhausted")
        )
        return None
    if m.expires_at is not None and m.expires_at <= now():
        await session.execute(
            update(Membership).where(Membership.id == m.id).values(status="expired")
        )
        return None
    return m


async def deduct_balance(
    session: AsyncSession, *, membership_id: uuid.UUID, amount: Decimal
) -> None:
    """Atomic deduction. Sets status='exhausted' when balance drops to zero.

    Raises ``DomainError`` if the membership doesn't have enough balance.
    """
    result = await session.execute(
        update(Membership)
        .where(
            Membership.id == membership_id,
            Membership.status == "active",
            Membership.balance_remaining >= amount,
        )
        .values(balance_remaining=Membership.balance_remaining - amount)
    )
    if result.rowcount != 1:
        raise DomainError(
            "Недостаточно средств на VIP-балансе. "
            "Уменьшите количество или выберите в селекте конкретную акцию "
            "(тогда покупка пройдёт по обычной цене со штампом/кэшбэком), "
            "или продайте новый абонемент."
        )

    # If we just drained the balance, mark the membership exhausted so the
    # next purchase doesn't pretend it's still active.
    new_balance = (await session.execute(
        select(Membership.balance_remaining).where(Membership.id == membership_id)
    )).scalar_one()
    if new_balance is not None and Decimal(new_balance) <= 0:
        await session.execute(
            update(Membership).where(Membership.id == membership_id)
            .values(status="exhausted")
        )


async def cancel_membership(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    membership_id: uuid.UUID | None = None,
) -> Membership | None:
    """Cancel a customer's active VIP membership ("remove the campaign").

    Flips status to ``cancelled`` and stamps ``cancelled_at``. Returns the
    cancelled membership, or ``None`` if the customer had no active one.
    Remaining deposit balance is NOT auto-refunded — issue a manual cashback
    grant if the business wants to return it. The caller owns audit + the
    dashboard projection refresh.
    """
    stmt = (
        select(Membership)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
        .with_for_update()
    )
    if membership_id is not None:
        stmt = stmt.where(Membership.id == membership_id)
    m = (await session.execute(stmt)).scalar_one_or_none()
    if m is None:
        return None

    await session.execute(
        update(Membership)
        .where(Membership.id == m.id, Membership.status == "active")
        .values(status="cancelled", cancelled_at=now())
    )
    return m


async def activate_membership(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
    staff_id: uuid.UUID,
    campaign_id: uuid.UUID,
    amount_paid: Decimal,
    client_request_id: str,
    currency: str = "UZS",
) -> Membership:
    """Sell a VIP deposit to a customer.

    The full ``amount_paid`` lands on ``balance_remaining``. If the campaign
    rules also specify a hard expiry, that is honoured — otherwise VIP lives
    until the deposit is drained.
    """
    camp = (await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.type == "tiered_status",
            Campaign.status == "active",
        )
    )).scalar_one_or_none()
    if camp is None:
        raise CampaignNotApplicable(
            "Выбранная акция-абонемент не существует или не активна"
        )

    rules = camp.rules or {}
    discount_percent = int(rules.get("discount_percent", 10))
    duration_days = int(rules.get("duration_days") or 0)
    entry_amount = Decimal(str(rules.get("entry_amount", 0)))

    if amount_paid < entry_amount:
        raise DomainError(
            f"Минимальная сумма для активации этой акции — {entry_amount} {currency}"
        )

    existing = await get_active_membership(
        session, tenant_id=tenant_id, user_id=user_id
    )
    if existing is not None:
        raise DomainError(
            "У клиента уже есть активный абонемент. Дождитесь окончания текущего."
        )

    tx = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        staff_id=staff_id,
        type="manual_grant",
        status="committed",
        total_amount=amount_paid,
        currency=currency,
        source="admin_panel",
        client_request_id=client_request_id,
        notes=f"VIP membership: {camp.name}",
        metadata_={
            "grant_kind": "membership_activation",
            "campaign_id": str(campaign_id),
            "discount_percent": discount_percent,
            "duration_days": duration_days,
        },
    )
    session.add(tx)
    await session.flush()

    expires_at = now() + timedelta(days=duration_days) if duration_days > 0 else None
    membership = Membership(
        tenant_id=tenant_id,
        user_id=user_id,
        campaign_id=campaign_id,
        discount_percent=discount_percent,
        amount_paid=amount_paid,
        balance_remaining=amount_paid,
        status="active",
        expires_at=expires_at,
        activated_by=staff_id,
    )
    session.add(membership)
    await session.flush()
    return membership
