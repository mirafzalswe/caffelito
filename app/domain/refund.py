"""Refund — compensating transaction for a previously committed purchase or
prepaid consumption.

What this implements (closes Acceptance §A.4):

* purchase  — reverse stamps awarded, claw back cashback earned, restore
  prepaid units that were consumed as part of the line items
* prepaid_consume — restore one unit on the affected package

What this intentionally does NOT support in MVP:

* refunding a redeem_free — a free coffee that was already handed to the
  customer cannot be ungiven without business policy on whether to
  re-open the card. Plan §4.7 leaves this for V2.
* refund-of-refund — once reversed, a transaction can't be refunded again.

The flow runs inside the caller's DB transaction (``session_scope``) so
that the reverse tx, the inverse ledger entries and the projection
update all commit atomically.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.domain import events
from app.domain.audit import record_audit
from app.domain.errors import RefundNotAllowed, TransactionNotFound
from app.domain.idempotency import find_replay
from app.domain.outbox import enqueue_event
from app.models import (
    CashbackWallet,
    LedgerEntry,
    LoyaltyCard,
    PrepaidPackage,
    Transaction,
    WalletEntry,
)


REFUNDABLE_TYPES = ("purchase", "prepaid_consume")


async def refund_transaction(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    staff_id: uuid.UUID,
    transaction_id: uuid.UUID,
    reason: str,
    client_request_id: str,
) -> uuid.UUID:
    """Refund a committed transaction. Returns the new (refund) transaction id."""

    # Idempotency — same client_request_id replays the original refund.
    # Scoped by type so we never confuse a refund key with the original
    # purchase that may have shared the same UUID.
    replay = await find_replay(
        session,
        tenant_id=tenant_id,
        client_request_id=client_request_id,
        expected_type="refund",
    )
    if replay is not None:
        return replay.id

    # ---- 1. load + lock the original transaction ---------------------------
    orig_stmt = (
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    orig = (await session.execute(orig_stmt)).scalar_one_or_none()
    if orig is None:
        raise TransactionNotFound

    if orig.type not in REFUNDABLE_TYPES:
        raise RefundNotAllowed(
            f"Transactions of type '{orig.type}' cannot be refunded"
        )
    if orig.status != "committed":
        raise RefundNotAllowed(
            f"Transaction is in status '{orig.status}', refund not allowed"
        )

    # ---- 2. fetch the original ledger entries (the authoritative effects) --
    ledger_stmt = select(LedgerEntry).where(
        LedgerEntry.transaction_id == orig.id
    )
    original_entries = list(
        (await session.execute(ledger_stmt)).scalars().all()
    )

    # ---- 3. create the reverse transaction ---------------------------------
    reverse = Transaction(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=orig.user_id,
        staff_id=staff_id,
        type="refund",
        status="committed",
        total_amount=-orig.total_amount,
        currency=orig.currency,
        payment_method=orig.payment_method,
        source="staff_bot",
        client_request_id=client_request_id,
        reverses=orig.id,
        notes=reason[:500] if reason else None,
        metadata_={"reversed_tx_id": str(orig.id), "reason": reason or ""},
    )
    session.add(reverse)
    await session.flush()

    # Mark the original as reversed.
    await session.execute(
        update(Transaction)
        .where(Transaction.id == orig.id, Transaction.status == "committed")
        .values(status="reversed", reversed_by=reverse.id)
    )

    # ---- 4. compensate each ledger account --------------------------------
    cards_touched: set[uuid.UUID] = set()
    packages_touched: set[uuid.UUID] = set()

    for entry in original_entries:
        await _compensate_ledger(
            session,
            tenant_id=tenant_id,
            user_id=orig.user_id,
            reverse_tx_id=reverse.id,
            entry=entry,
            cards_touched=cards_touched,
            packages_touched=packages_touched,
            reason=reason,
        )

    # ---- 5. domain event + audit ------------------------------------------
    await enqueue_event(
        session,
        tenant_id=tenant_id,
        aggregate_type=events.AGG_TRANSACTION,
        aggregate_id=orig.id,
        type_=events.EVT_TRANSACTION_REFUNDED,
        payload={
            "transaction_id": str(orig.id),
            "refund_transaction_id": str(reverse.id),
            "user_id": str(orig.user_id),
            "branch_id": str(branch_id),
            "reason": reason or "",
        },
    )

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_type="staff",
        actor_id=staff_id,
        action="transaction.refund",
        target_type="transaction",
        target_id=orig.id,
        before={"status": "committed"},
        after={"status": "reversed", "reversed_by": str(reverse.id)},
        reason=reason,
    )

    # Refresh the dashboard projection so subsequent reads see the rollback.
    from app.domain.loyalty_engine import _refresh_user_dashboard_projection

    await _refresh_user_dashboard_projection(session, user_id=orig.user_id)

    return reverse.id


# ----------------------------------------------------------------------------
# Internals — per-account compensation
# ----------------------------------------------------------------------------


async def _compensate_ledger(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    reverse_tx_id: uuid.UUID,
    entry: LedgerEntry,
    cards_touched: set[uuid.UUID],
    packages_touched: set[uuid.UUID],
    reason: str | None,
) -> None:
    """Mirror one original ledger row with its inverse and reverse the side
    effect on the projection that the original row created."""

    # 5.a. write the inverse ledger row.
    session.add(
        LedgerEntry(
            tenant_id=tenant_id,
            user_id=user_id,
            transaction_id=reverse_tx_id,
            account=entry.account,
            delta=-entry.delta,
            unit=entry.unit,
            reason=f"refund:{entry.reason}",
        )
    )

    # 5.b. dispatch by account family.
    account = entry.account
    if account.startswith("card:") and entry.unit == "stamp":
        campaign_id = uuid.UUID(account.split(":", 1)[1])
        await _refund_stamps(
            session,
            user_id=user_id,
            campaign_id=campaign_id,
            stamps_to_refund=int(entry.delta),
        )
        cards_touched.add(campaign_id)
    elif account.startswith("prepaid:") and entry.unit == "coffee_unit":
        package_id = uuid.UUID(account.split(":", 1)[1])
        await _refund_prepaid(
            session,
            package_id=package_id,
            delta=int(entry.delta),
        )
        packages_touched.add(package_id)
    elif account == "wallet:cashback" and entry.unit == "currency":
        delta = Decimal(entry.delta)
        if delta > 0:
            # The original purchase EARNED cashback — claw it back.
            await _refund_cashback(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                amount=delta,
                reverse_tx_id=reverse_tx_id,
                reason=reason,
            )
        elif delta < 0:
            # The original purchase was paid (partly) WITH cashback — give it back.
            await _restore_cashback(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                amount=-delta,
                reverse_tx_id=reverse_tx_id,
            )


async def _refund_stamps(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    campaign_id: uuid.UUID,
    stamps_to_refund: int,
) -> None:
    """Reverse stamps from the most recently advanced card of the campaign.

    Strategy: walk the user's cards for this campaign from newest first; for
    each, decrement up to ``stamps_to_refund`` stamps; if the card was
    ``complete`` we re-open it; if it had been ``redeemed`` we cannot
    safely roll it back (the customer already received the free coffee) —
    in that case the stamps were already "spent" and no further action is
    required for that card.
    """
    if stamps_to_refund <= 0:
        return
    remaining = stamps_to_refund

    cards = list(
        (
            await session.execute(
                select(LoyaltyCard)
                .where(
                    LoyaltyCard.user_id == user_id,
                    LoyaltyCard.campaign_id == campaign_id,
                    LoyaltyCard.status.in_(("open", "complete")),
                )
                .order_by(LoyaltyCard.opened_at.desc())
                .with_for_update()
            )
        ).scalars().all()
    )

    for card in cards:
        if remaining <= 0:
            break
        take = min(remaining, card.stamps)
        if take <= 0:
            continue
        new_stamps = card.stamps - take
        new_status = "open" if (card.status == "complete" or new_stamps < card.stamps_required) else card.status
        await session.execute(
            update(LoyaltyCard)
            .where(LoyaltyCard.id == card.id, LoyaltyCard.version == card.version)
            .values(
                stamps=new_stamps,
                status=new_status,
                completed_at=None if new_status == "open" else card.completed_at,
                version=LoyaltyCard.version + 1,
            )
        )
        remaining -= take
    # If `remaining > 0` here, the rest of the stamps map to cards that
    # were already redeemed — we accept that as the customer keeping the
    # free coffee. The inverse ledger entry above keeps the audit trail.


async def _refund_prepaid(
    session: AsyncSession,
    *,
    package_id: uuid.UUID,
    delta: int,
) -> None:
    """Reverse a prepaid effect.

    For ``delta < 0`` (the original was a consume) we restore that many
    units. For ``delta > 0`` (the original was an open) we cancel the
    package by setting it to ``refunded`` and zeroing the remaining qty.
    """
    if delta < 0:
        restore = -delta  # original consumed N → restore N units
        await session.execute(
            update(PrepaidPackage)
            .where(PrepaidPackage.id == package_id)
            .values(
                qty_remaining=PrepaidPackage.qty_remaining + restore,
                # If the package was closed as exhausted, re-open it.
                status="active",
                closed_at=None,
                version=PrepaidPackage.version + 1,
            )
        )
    elif delta > 0:
        await session.execute(
            update(PrepaidPackage)
            .where(PrepaidPackage.id == package_id)
            .values(
                qty_remaining=0,
                status="refunded",
                closed_at=now(),
                version=PrepaidPackage.version + 1,
            )
        )


async def _refund_cashback(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: Decimal,
    reverse_tx_id: uuid.UUID,
    reason: str | None,
) -> None:
    """Claw back cashback that was earned on the reversed transaction.

    Posts a wallet_entry with kind='refund' and a negative amount, capped
    at the current wallet balance so we never drive the balance below
    zero. If the customer already spent the cashback we accept the
    shortfall — the inverse ledger row preserves the audit trail.
    """
    if amount <= 0:
        return

    wallet_stmt = (
        select(CashbackWallet)
        .where(CashbackWallet.user_id == user_id)
        .order_by(CashbackWallet.currency.asc())
        .with_for_update()
    )
    wallets = list((await session.execute(wallet_stmt)).scalars().all())
    if not wallets:
        return

    # Charge the first wallet (single-currency MVP); if multi-currency we
    # match by currency in V2.
    wallet = wallets[0]
    cap = min(amount, Decimal(wallet.balance))
    if cap <= 0:
        return

    idem = f"refund:{reverse_tx_id}"
    inserted = (
        await session.execute(
            insert(WalletEntry)
            .values(
                wallet_id=wallet.id,
                amount=-cap,
                kind="refund",
                source_type="transaction",
                source_id=reverse_tx_id,
                idempotency_key=idem,
            )
            .on_conflict_do_nothing(index_elements=["wallet_id", "idempotency_key"])
            .returning(WalletEntry.id)
        )
    ).scalar_one_or_none()
    if inserted is None:
        return  # replay

    await session.execute(
        update(CashbackWallet)
        .where(CashbackWallet.id == wallet.id)
        .values(
            balance=CashbackWallet.balance - cap,
            version=CashbackWallet.version + 1,
        )
    )


async def _restore_cashback(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: Decimal,
    reverse_tx_id: uuid.UUID,
) -> None:
    """Give back cashback that was SPENT on the reversed purchase.

    The mirror of ``_refund_cashback``: credits the customer's wallet with a
    ``kind='refund'`` entry so a refunded cashback-paid purchase returns the
    balance the customer put in.
    """
    if amount <= 0:
        return

    wallet = (
        await session.execute(
            select(CashbackWallet)
            .where(CashbackWallet.user_id == user_id)
            .order_by(CashbackWallet.currency.asc())
        )
    ).scalars().first()
    if wallet is None:
        return  # no wallet means nothing was ever spent — defensive

    from app.domain.wallet import credit

    await credit(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        currency=wallet.currency,
        amount=amount,
        source_type="transaction",
        source_id=reverse_tx_id,
        idempotency_key=f"refund_spend:{reverse_tx_id}",
        kind="refund",
    )
