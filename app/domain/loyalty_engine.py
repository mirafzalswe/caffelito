"""Punchcard / cashback / bonus / prepaid evaluation engine.

Public entry point: ``record_purchase``.

The engine evaluates *every* active campaign of types ``punchcard`` and
``cashback`` (and bonus_item, in V2) against the incoming purchase lines and
applies effects atomically:

    1. dedupe via client_request_id
    2. open Transaction + TransactionItem rows
    3. for each loyalty-eligible unit, advance an existing punchcard or open
       a new one — using SELECT ... FOR UPDATE on the active card
    4. emit ledger entries for stamps and cashback
    5. update the user_dashboard projection
    6. enqueue domain events to the outbox

All in a single DB transaction owned by the caller (``session_scope``).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.config import settings
from app.domain import events
from app.domain.errors import (
    CampaignNotApplicable,
    ConcurrentUpdate,
)
from app.domain.idempotency import find_replay
from app.domain.outbox import enqueue_event
from app.domain.schemas import PurchaseRequest, PurchaseResult
from app.models import (
    Campaign,
    CampaignBranch,
    CampaignProduct,
    LedgerEntry,
    LoyaltyCard,
    Membership,
    Product,
    Transaction,
    TransactionItem,
)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


async def record_purchase(
    session: AsyncSession,
    *,
    request: PurchaseRequest,
) -> PurchaseResult:
    """Record a purchase and apply all matching loyalty rules.

    The whole flow is wrapped in the caller's DB transaction (``session_scope``).
    On replay (same ``client_request_id``) the original result is returned and
    no new state is mutated.
    """
    # ---- 1. idempotency check ------------------------------------------------
    replay = await find_replay(
        session,
        tenant_id=request.tenant_id,
        client_request_id=request.client_request_id,
        expected_type="purchase",
    )
    if replay is not None:
        return await _materialize_replay_result(session, replay)

    if not request.lines:
        raise CampaignNotApplicable("Empty purchase")

    # ---- 2. fetch products in batch -----------------------------------------
    products_by_id = await _load_products(
        session,
        tenant_id=request.tenant_id,
        product_ids=[ln.product_id for ln in request.lines],
    )

    # ---- 3. compute totals ---------------------------------------------------
    # VIP membership (deposit-style) discounts every line and drains the
    # deposit — but ONLY in the auto path. If the admin explicitly picked a
    # campaign in the dropdown (``force_campaign_id``), they want that campaign
    # applied at full price, bypassing VIP. This is the escape hatch when
    # the VIP balance is too low to cover the purchase.
    from app.domain.membership import deduct_balance, get_active_membership

    if request.force_campaign_id is None:
        membership = await get_active_membership(
            session, tenant_id=request.tenant_id, user_id=request.user_id
        )
    else:
        membership = None
    discount_factor = (
        Decimal("1.00") - Decimal(membership.discount_percent) / Decimal(100)
        if membership is not None else None
    )

    total_amount = Decimal("0.00")
    total_saved = Decimal("0.00")
    items_to_insert: list[TransactionItem] = []
    for ln in request.lines:
        product = products_by_id[ln.product_id]
        base_price = ln.unit_price if ln.unit_price is not None else product.base_price
        if discount_factor is not None and ln.paid_with == "money":
            unit_price = (base_price * discount_factor).quantize(Decimal("0.01"))
            line_discount = ((base_price - unit_price) * ln.qty).quantize(Decimal("0.01"))
            total_saved += line_discount
        else:
            unit_price = base_price
            line_discount = Decimal("0.00")
        if ln.paid_with == "money":
            total_amount += unit_price * ln.qty
        items_to_insert.append(
            TransactionItem(
                product_id=ln.product_id,
                qty=ln.qty,
                unit_price=unit_price,
                discount=line_discount,
                paid_with=ln.paid_with,
            )
        )

    # If VIP — drain the deposit BEFORE inserting the transaction; raises
    # DomainError when balance is short, so the call rolls back cleanly.
    vip_charged: Decimal | None = None
    vip_balance_after: Decimal | None = None
    if membership is not None and total_amount > 0:
        await deduct_balance(
            session, membership_id=membership.id, amount=total_amount,
        )
        vip_charged = total_amount
        # Read post-deduction balance for the notification/result payload.
        vip_balance_after = (await session.execute(
            select(Membership.balance_remaining).where(Membership.id == membership.id)
        )).scalar_one()

    tx_metadata: dict = {}
    if membership is not None:
        tx_metadata = {
            "membership_id": str(membership.id),
            "vip_discount_percent": membership.discount_percent,
            "vip_discount_amount": str(total_saved),
            "vip_charged": str(vip_charged) if vip_charged else None,
        }

    # ---- 4. insert transaction ----------------------------------------------
    tx = Transaction(
        tenant_id=request.tenant_id,
        branch_id=request.branch_id,
        user_id=request.user_id,
        staff_id=request.staff_id,
        type="purchase",
        status="committed",
        total_amount=total_amount,
        currency=request.currency,
        payment_method=request.payment_method,
        source=request.source,
        client_request_id=request.client_request_id,
        notes=request.notes,
        metadata_=tx_metadata,
    )
    session.add(tx)
    await session.flush()

    for item in items_to_insert:
        item.transaction_id = tx.id
        session.add(item)

    # ---- 5. evaluate campaigns ----------------------------------------------
    active_campaigns = await _load_active_campaigns(
        session,
        tenant_id=request.tenant_id,
        branch_id=request.branch_id,
        product_ids=list({ln.product_id for ln in request.lines}),
    )

    result = PurchaseResult(
        transaction_id=tx.id,
        is_replay=False,
        vip_charged=vip_charged,
        vip_balance_remaining=vip_balance_after,
    )

    # VIP membership is exclusive — while it's active the customer's perk
    # was already paid out as a discount, so no stamps and no cashback.
    if membership is not None:
        punchcards: list[Campaign] = []
        cashbacks: list[Campaign] = []
    elif request.force_campaign_id is not None:
        # Admin explicitly picked ONE campaign — load it directly, bypassing
        # the branch/scope filter (admin override is intentional), but verify
        # tenant + active + supported type. Dispatch by type below.
        forced = (
            await session.execute(
                select(Campaign).where(
                    Campaign.id == request.force_campaign_id,
                    Campaign.tenant_id == request.tenant_id,
                    Campaign.status == "active",
                )
            )
        ).scalar_one_or_none()
        if forced is None:
            raise CampaignNotApplicable(
                "Выбранная акция не существует, не активна или принадлежит другому магазину"
            )
        if forced.type == "punchcard":
            punchcards, cashbacks = [forced], []
        elif forced.type == "cashback":
            punchcards, cashbacks = [], [forced]
        else:
            raise CampaignNotApplicable(
                f"Акцию типа «{forced.type}» нельзя применить при выдаче кофе"
            )
    else:
        # Auto path: apply every matching campaign by stackable+priority rules.
        punchcards = _resolve_stackable(
            [c for c in active_campaigns if c.type == "punchcard"]
        )
        cashbacks = _resolve_stackable(
            [c for c in active_campaigns if c.type == "cashback"]
        )

    for campaign in punchcards:
        await _apply_punchcard(
            session,
            campaign=campaign,
            request=request,
            tx_id=tx.id,
            products_by_id=products_by_id,
            result=result,
        )

    for campaign in cashbacks:
        await _apply_cashback(
            session,
            campaign=campaign,
            request=request,
            tx_id=tx.id,
            money_amount=total_amount,
            result=result,
        )

    # ---- 6. dashboard projection (handled in side-effect job) ----------------
    # We let an event consumer rebuild user_dashboard. For MVP, do it inline:
    await _refresh_user_dashboard_projection(session, user_id=request.user_id)

    # ---- 7. outbox ----------------------------------------------------------
    await enqueue_event(
        session,
        tenant_id=request.tenant_id,
        aggregate_type=events.AGG_TRANSACTION,
        aggregate_id=tx.id,
        type_=events.EVT_PURCHASE_RECORDED,
        payload={
            "transaction_id": str(tx.id),
            "user_id": str(request.user_id),
            "branch_id": str(request.branch_id),
            "total_amount": str(total_amount),
            "stamps_added": {str(k): v for k, v in result.stamps_added_per_card.items()},
            "cards_completed": [str(c) for c in result.cards_completed],
            "free_coffees_unlocked": result.free_coffees_unlocked,
            "cashback_earned": str(result.cashback_earned),
        },
    )

    return result


# ----------------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------------


async def _materialize_replay_result(
    session: AsyncSession,
    tx: Transaction,
) -> PurchaseResult:
    """Reconstruct a PurchaseResult shape from an already-committed transaction."""
    return PurchaseResult(transaction_id=tx.id, is_replay=True)


async def _load_products(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, Product]:
    if not product_ids:
        return {}
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
    )
    rows = (await session.execute(stmt)).scalars().all()
    by_id = {p.id: p for p in rows}
    missing = set(product_ids) - by_id.keys()
    if missing:
        raise CampaignNotApplicable(f"Unknown products: {sorted(missing)}")
    return by_id


async def _load_active_campaigns(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> list[Campaign]:
    """Active campaigns for this branch that touch any of the products."""
    now_ts = now()
    branch_match = exists().where(
        and_(
            CampaignBranch.campaign_id == Campaign.id,
            CampaignBranch.branch_id == branch_id,
        )
    )
    # campaign_products is optional — empty rows mean "all products of this tenant"
    has_product_scope = exists().where(CampaignProduct.campaign_id == Campaign.id)
    product_match = exists().where(
        and_(
            CampaignProduct.campaign_id == Campaign.id,
            CampaignProduct.product_id.in_(product_ids),
        )
    )
    stmt = (
        select(Campaign)
        .where(
            Campaign.tenant_id == tenant_id,
            Campaign.status == "active",
            (Campaign.starts_at <= now_ts),
            ((Campaign.ends_at.is_(None)) | (Campaign.ends_at > now_ts)),
            branch_match,
        )
        .where(~has_product_scope | product_match)
        .order_by(Campaign.priority.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _apply_punchcard(
    session: AsyncSession,
    *,
    campaign: Campaign,
    request: PurchaseRequest,
    tx_id: uuid.UUID,
    products_by_id: dict[uuid.UUID, Product],
    result: PurchaseResult,
) -> None:
    """Add stamps for each loyalty-eligible unit; roll cards over at completion."""
    rules = campaign.rules or {}
    trigger = rules.get("trigger", {})
    stamps_required: int = int(rules.get("stamps_required", 10))
    expires_after_days: int | None = rules.get("expires_after_days") or settings.punchcard_default_expires_days
    cooldown_min: int = int(rules.get("cooldown_minutes", settings.punchcard_default_cooldown_min))

    eligible_lines = [
        ln for ln in request.lines
        if ln.paid_with in ("money", "prepaid")  # 'free' redemptions don't earn new stamps
        and _line_matches_trigger(products_by_id[ln.product_id], trigger)
    ]
    total_units = sum(ln.qty for ln in eligible_lines)
    if total_units == 0:
        return

    # Cooldown — last stamp on any active card for this campaign
    if cooldown_min > 0:
        recent_stmt = select(func.max(LedgerEntry.created_at)).where(
            LedgerEntry.tenant_id == request.tenant_id,
            LedgerEntry.user_id == request.user_id,
            LedgerEntry.account == f"card:{campaign.id}",
            LedgerEntry.unit == "stamp",
        )
        last_ts = (await session.execute(recent_stmt)).scalar_one_or_none()
        if last_ts is not None:
            delta_min = (now() - last_ts).total_seconds() / 60.0
            if delta_min < cooldown_min:
                # Soft-skip; treat the units as non-eligible due to cooldown.
                # We do NOT raise so that the purchase still records.
                return

    units_left = total_units
    while units_left > 0:
        card = await _get_or_create_active_card(
            session,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            campaign_id=campaign.id,
            stamps_required=stamps_required,
            expires_after_days=expires_after_days,
        )
        # Capture pre-update values before SQLAlchemy auto-syncs card.stamps
        # to the new server-side value via the synchronize_session='auto' policy.
        prev_stamps = card.stamps
        room = card.stamps_required - prev_stamps
        take = min(units_left, room)
        new_total = prev_stamps + take
        will_complete = new_total >= card.stamps_required

        # Bump card with optimistic concurrency check (version). If we are also
        # completing the card on this stamp, transition to 'complete' atomically
        # in the same UPDATE so the partial unique index stays consistent.
        new_status = "complete" if will_complete else "open"
        completed_at = now() if will_complete else None
        upd = (
            update(LoyaltyCard)
            .where(
                LoyaltyCard.id == card.id,
                LoyaltyCard.version == card.version,
                LoyaltyCard.status == "open",
            )
            .values(
                stamps=LoyaltyCard.stamps + take,
                status=new_status,
                completed_at=completed_at,
                version=LoyaltyCard.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        res = await session.execute(upd)
        if res.rowcount != 1:
            # Optimistic lock lost the race — bail without touching the
            # caller's session (the outer session_scope will rollback).
            raise ConcurrentUpdate(
                "Concurrent stamp update on loyalty card; retry the operation"
            )

        # Keep the ORM-cached card object in sync for downstream loop iterations
        # (we still reference it later in this function).
        card.stamps = new_total
        card.version = card.version + 1
        if will_complete:
            card.status = "complete"
            card.completed_at = completed_at

        # Ledger
        session.add(
            LedgerEntry(
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                transaction_id=tx_id,
                account=f"card:{campaign.id}",
                delta=Decimal(take),
                unit="stamp",
                reason="punchcard_stamp",
            )
        )

        result.stamps_added_per_card[card.id] = (
            result.stamps_added_per_card.get(card.id, 0) + take
        )

        if will_complete:
            # Status was already flipped to 'complete' in the UPDATE above —
            # we just emit the domain event here.
            result.cards_completed.append(card.id)
            result.free_coffees_unlocked += 1
            await enqueue_event(
                session,
                tenant_id=request.tenant_id,
                aggregate_type=events.AGG_LOYALTY_CARD,
                aggregate_id=card.id,
                type_=events.EVT_FREE_UNLOCKED,
                payload={
                    "user_id": str(request.user_id),
                    "card_id": str(card.id),
                    "campaign_id": str(campaign.id),
                },
            )

        units_left -= take


async def _get_or_create_active_card(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    campaign_id: uuid.UUID,
    stamps_required: int,
    expires_after_days: int | None,
) -> LoyaltyCard:
    """Lock and return the open card; create one if none exists."""
    stmt = (
        select(LoyaltyCard)
        .where(
            LoyaltyCard.user_id == user_id,
            LoyaltyCard.campaign_id == campaign_id,
            LoyaltyCard.status == "open",
        )
        .with_for_update()
    )
    card = (await session.execute(stmt)).scalar_one_or_none()
    if card is not None:
        return card

    expires_at = None
    if expires_after_days:
        from datetime import timedelta

        expires_at = now() + timedelta(days=int(expires_after_days))

    card = LoyaltyCard(
        tenant_id=tenant_id,
        user_id=user_id,
        campaign_id=campaign_id,
        stamps=0,
        stamps_required=stamps_required,
        status="open",
        expires_at=expires_at,
    )
    session.add(card)
    await session.flush()
    return card


async def _apply_cashback(
    session: AsyncSession,
    *,
    campaign: Campaign,
    request: PurchaseRequest,
    tx_id: uuid.UUID,
    money_amount: Decimal,
    result: PurchaseResult,
) -> None:
    """Earn cashback as a percentage of money paid. Wallet logic lives in domain.wallet.

    Rule schema (current admin form): ``{percent: 5, min_amount: 0, expires_after_days: 180}``
    where ``percent`` is human-readable percent (5 = 5%). Legacy rows may use
    ``rate`` as a fraction (0.05); we accept both for back-compat.
    """
    if money_amount <= 0:
        return
    rules = campaign.rules or {}

    if "percent" in rules:
        rate = Decimal(str(rules["percent"])) / Decimal(100)
    else:
        rate = Decimal(str(rules.get("rate", 0)))
    if rate <= 0:
        return

    min_amount = Decimal(str(rules.get("min_amount", 0)))
    if money_amount < min_amount:
        return

    earn_amount = (money_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if earn_amount <= 0:
        return

    # Defer wallet-row update to wallet service — avoids circular concerns.
    from app.domain.wallet import credit  # local import to keep modules decoupled

    await credit(
        session,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        currency=request.currency,
        amount=earn_amount,
        source_type="transaction",
        source_id=tx_id,
        idempotency_key=f"earn:{tx_id}",
        expires_after_days=int(rules.get("expires_after_days", 0)) or None,
    )

    session.add(
        LedgerEntry(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            transaction_id=tx_id,
            account="wallet:cashback",
            delta=earn_amount,
            unit="currency",
            reason="cashback_earn",
        )
    )

    result.cashback_earned += earn_amount

    await enqueue_event(
        session,
        tenant_id=request.tenant_id,
        aggregate_type=events.AGG_WALLET,
        aggregate_id=request.user_id,
        type_=events.EVT_CASHBACK_EARNED,
        payload={
            "user_id": str(request.user_id),
            "amount": str(earn_amount),
            "currency": request.currency,
            "transaction_id": str(tx_id),
        },
    )


def _resolve_stackable(campaigns: list[Campaign]) -> list[Campaign]:
    """Filter a same-type campaign list by stackable + priority rules.

    Walk campaigns highest-priority first. The first one is always taken; each
    later one is taken only if it is stackable AND every already-taken campaign
    is stackable. So a non-stackable winner blocks everything below it, and a
    non-stackable loser is dropped because it cannot combine with the winners
    above it.
    """
    if len(campaigns) <= 1:
        return campaigns
    # Tie-break: at equal priority, a non-stackable campaign wins. Otherwise
    # the picked winner depends on insertion order (database row order), which
    # is opaque to the admin.
    ordered = sorted(
        campaigns,
        key=lambda c: (-(c.priority or 0), bool(c.stackable)),
    )
    selected: list[Campaign] = []
    for c in ordered:
        if not selected:
            selected.append(c)
            if not c.stackable:
                break
            continue
        if c.stackable and all(s.stackable for s in selected):
            selected.append(c)
    return selected


def _line_matches_trigger(product: Product, trigger: dict[str, Any]) -> bool:
    """Decide whether a product line counts toward a campaign trigger.

    Supported keys: ``product_category``, ``product_id``, ``min_size`` (S<M<L),
    ``loyalty_eligible_only`` (default True).
    """
    if trigger.get("loyalty_eligible_only", True) and not product.is_loyalty_eligible:
        return False
    if (cat := trigger.get("product_category")) and product.category != cat:
        return False
    if (pid := trigger.get("product_id")) and str(product.id) != str(pid):
        return False
    if min_size := trigger.get("min_size"):
        order = {"S": 0, "M": 1, "L": 2, "XL": 3}
        if (
            product.size is not None
            and order.get(product.size, -1) < order.get(str(min_size), 99)
        ):
            return False
    return True


# ----------------------------------------------------------------------------
# Projection refresh
# ----------------------------------------------------------------------------


async def _refresh_user_dashboard_projection(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> None:
    """Recompute the full ``user_dashboard`` projection from authoritative tables.

    Fields covered:

    * ``stamps_total`` / ``stamps_required`` — latest open card.
    * ``free_coffees_available`` — count of complete cards.
    * ``cashback_balance`` — sum across all wallets (single-ccy MVP).
    * ``prepaid_remaining`` — sum of active package qty_remaining.
    * ``last_visit_at`` / ``last_visit_branch_id`` — newest transaction.
    * ``visits_30d`` — number of distinct days with a transaction in the
      trailing 30-day window (a "visit" = one or more transactions on a
      single calendar day, evaluated in UTC for MVP).
    """
    from sqlalchemy import text

    await session.execute(
        text(
            """
            WITH latest_tx AS (
                SELECT branch_id, created_at
                  FROM transactions
                 WHERE user_id = :uid
                 ORDER BY created_at DESC
                 LIMIT 1
            )
            INSERT INTO user_dashboard
                (user_id, tenant_id, stamps_total, stamps_required,
                 free_coffees_available, cashback_balance, prepaid_remaining,
                 last_visit_at, last_visit_branch_id, visits_30d, updated_at)
            SELECT
                u.id, u.tenant_id,
                COALESCE((
                    SELECT lc.stamps FROM loyalty_cards lc
                    WHERE lc.user_id = u.id AND lc.status = 'open'
                    ORDER BY lc.opened_at DESC LIMIT 1
                ), 0),
                COALESCE((
                    SELECT lc.stamps_required FROM loyalty_cards lc
                    WHERE lc.user_id = u.id AND lc.status = 'open'
                    ORDER BY lc.opened_at DESC LIMIT 1
                ), 0),
                (SELECT COUNT(*) FROM loyalty_cards
                  WHERE user_id = u.id AND status = 'complete'),
                COALESCE((
                    SELECT SUM(balance) FROM cashback_wallets WHERE user_id = u.id
                ), 0),
                COALESCE((
                    SELECT SUM(qty_remaining) FROM prepaid_packages
                     WHERE user_id = u.id AND status = 'active'
                ), 0),
                (SELECT created_at FROM latest_tx),
                (SELECT branch_id  FROM latest_tx),
                COALESCE((
                    SELECT COUNT(DISTINCT (created_at AT TIME ZONE 'UTC')::date)
                      FROM transactions
                     WHERE user_id = u.id
                       AND created_at >= now() - INTERVAL '30 days'
                ), 0),
                now()
            FROM users u
            WHERE u.id = :uid
            ON CONFLICT (user_id) DO UPDATE SET
                stamps_total           = EXCLUDED.stamps_total,
                stamps_required        = EXCLUDED.stamps_required,
                free_coffees_available = EXCLUDED.free_coffees_available,
                cashback_balance       = EXCLUDED.cashback_balance,
                prepaid_remaining      = EXCLUDED.prepaid_remaining,
                last_visit_at          = EXCLUDED.last_visit_at,
                last_visit_branch_id   = EXCLUDED.last_visit_branch_id,
                visits_30d             = EXCLUDED.visits_30d,
                updated_at             = now();
            """
        ),
        {"uid": user_id},
    )
