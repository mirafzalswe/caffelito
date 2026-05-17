"""Cashback wallet — earn (credit) / spend (debit) / expire.

Balance is stored on cashback_wallets.balance for fast reads, and is the
projection of wallet_entries.amount sums. Spending is FIFO across earn rows
so that expiration semantics are correct.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.domain.errors import InsufficientCashback
from app.models import CashbackWallet, WalletEntry


# ---------------------------------------------------------------------------
# Wallet retrieval
# ---------------------------------------------------------------------------


async def get_or_create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    currency: str,
) -> CashbackWallet:
    stmt = select(CashbackWallet).where(
        CashbackWallet.tenant_id == tenant_id,
        CashbackWallet.user_id == user_id,
        CashbackWallet.currency == currency,
    )
    wallet = (await session.execute(stmt)).scalar_one_or_none()
    if wallet:
        return wallet

    wallet = CashbackWallet(
        tenant_id=tenant_id,
        user_id=user_id,
        currency=currency,
        balance=Decimal("0.00"),
    )
    session.add(wallet)
    await session.flush()
    return wallet


# ---------------------------------------------------------------------------
# Credit (earn / refund) — idempotent
# ---------------------------------------------------------------------------


async def credit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    currency: str,
    amount: Decimal,
    source_type: str,
    source_id: uuid.UUID | None,
    idempotency_key: str,
    expires_after_days: int | None = None,
    kind: str = "earn",
) -> None:
    if amount <= 0:
        return
    wallet = await get_or_create(
        session, tenant_id=tenant_id, user_id=user_id, currency=currency
    )

    expires_at = None
    if expires_after_days:
        expires_at = now() + timedelta(days=int(expires_after_days))

    # Idempotent insert into wallet_entries — ON CONFLICT means replay no-op.
    stmt = (
        insert(WalletEntry)
        .values(
            wallet_id=wallet.id,
            amount=amount,
            kind=kind,
            source_type=source_type,
            source_id=source_id,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["wallet_id", "idempotency_key"])
        .returning(WalletEntry.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is None:
        return  # replay — wallet already credited previously

    # Bump the projected balance (with version)
    await session.execute(
        update(CashbackWallet)
        .where(CashbackWallet.id == wallet.id)
        .values(
            balance=CashbackWallet.balance + amount,
            version=CashbackWallet.version + 1,
        )
    )


# ---------------------------------------------------------------------------
# Debit (spend) — FIFO across earn rows
# ---------------------------------------------------------------------------


async def debit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    currency: str,
    amount: Decimal,
    source_type: str,
    source_id: uuid.UUID | None,
    idempotency_key: str,
) -> None:
    """Spend ``amount`` from the wallet, FIFO across earn rows.

    Steps:
        1. Lock the wallet projection row to serialize concurrent debits.
        2. Idempotently insert the ``spend`` ledger row (no-op on replay).
        3. Walk non-exhausted, non-expired earn rows in FIFO order
           (``created_at`` asc) and bump ``spent_amount`` until the
           requested amount is allocated.
        4. Decrement the cached balance.

    Raises ``InsufficientCashback`` if the balance can't cover the spend.
    """
    if amount <= 0:
        return
    wallet = await get_or_create(
        session, tenant_id=tenant_id, user_id=user_id, currency=currency
    )

    # Lock the wallet row to serialize concurrent debits.
    locked_stmt = (
        select(CashbackWallet)
        .where(CashbackWallet.id == wallet.id)
        .with_for_update()
    )
    wallet = (await session.execute(locked_stmt)).scalar_one()

    if wallet.balance < amount:
        raise InsufficientCashback

    # Step 2 — idempotent spend row.
    stmt = (
        insert(WalletEntry)
        .values(
            wallet_id=wallet.id,
            amount=-amount,
            kind="spend",
            source_type=source_type,
            source_id=source_id,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["wallet_id", "idempotency_key"])
        .returning(WalletEntry.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is None:
        return  # replay

    # Step 3 — allocate FIFO across earn rows.
    earn_rows = list(
        (
            await session.execute(
                select(WalletEntry)
                .where(
                    WalletEntry.wallet_id == wallet.id,
                    WalletEntry.kind == "earn",
                    WalletEntry.amount > WalletEntry.spent_amount,
                    (WalletEntry.expires_at.is_(None))
                    | (WalletEntry.expires_at > now()),
                )
                .order_by(
                    WalletEntry.expires_at.asc().nullslast(),
                    WalletEntry.created_at.asc(),
                )
                .with_for_update()
            )
        ).scalars().all()
    )

    remaining = amount
    for earn in earn_rows:
        if remaining <= 0:
            break
        available = Decimal(earn.amount) - Decimal(earn.spent_amount)
        take = min(remaining, available)
        if take <= 0:
            continue
        await session.execute(
            update(WalletEntry)
            .where(WalletEntry.id == earn.id)
            .values(spent_amount=WalletEntry.spent_amount + take)
        )
        remaining -= take

    # Step 4 — projection.
    await session.execute(
        update(CashbackWallet)
        .where(CashbackWallet.id == wallet.id)
        .values(
            balance=CashbackWallet.balance - amount,
            version=CashbackWallet.version + 1,
        )
    )
