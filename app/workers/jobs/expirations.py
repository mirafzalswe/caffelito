"""Scheduled jobs: expire loyalty cards / prepaid packages / wallet entries."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.clock import now
from app.core.db import SessionLocal
from app.core.logging import get_logger

log = get_logger("worker.expirations")


async def expire_loyalty_cards(ctx: dict[str, Any]) -> int:  # noqa: ARG001
    """Mark open/complete cards as 'expired' once expires_at has passed."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE loyalty_cards
                   SET status = 'expired', version = version + 1
                 WHERE status IN ('open','complete')
                   AND expires_at IS NOT NULL
                   AND expires_at < :now
                RETURNING id
                """
            ),
            {"now": now()},
        )
        ids = result.scalars().all()
        await session.commit()
    if ids:
        log.info("loyalty_cards_expired", count=len(ids))
    return len(ids)


async def expire_prepaid_packages(ctx: dict[str, Any]) -> int:  # noqa: ARG001
    """Move active prepaid packages past expiry into 'expired' state."""
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE prepaid_packages
                   SET status = 'expired', closed_at = :now, version = version + 1
                 WHERE status = 'active'
                   AND expires_at IS NOT NULL
                   AND expires_at < :now
                RETURNING id
                """
            ),
            {"now": now()},
        )
        ids = result.scalars().all()
        await session.commit()
    if ids:
        log.info("prepaid_expired", count=len(ids))
    return len(ids)


async def expire_wallet_entries(ctx: dict[str, Any]) -> int:  # noqa: ARG001
    """Burn the still-unspent remainder of each earn row past its expiry.

    For each earn row with ``expires_at < now`` and ``spent_amount < amount``
    we:

    * insert a compensating ``expire`` wallet_entry for the *unspent*
      remainder (``amount - spent_amount``), idempotent via
      ``expire:<earn_id>``;
    * mark the earn row fully consumed by setting
      ``spent_amount = amount``, so the same row is never picked again;
    * decrement the cached wallet balance by the same remainder.

    This is the correctness fix that pairs with the FIFO debit allocator
    in ``app.domain.wallet.debit`` — without it, a partially-spent earn
    row would either burn balance twice (old behaviour) or silently leak
    spend allocation.
    """
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT we.id, we.wallet_id,
                           (we.amount - we.spent_amount) AS remainder
                    FROM wallet_entries we
                    LEFT JOIN wallet_entries comp
                           ON comp.idempotency_key = 'expire:' || we.id::text
                    WHERE we.kind = 'earn'
                      AND we.expires_at IS NOT NULL
                      AND we.expires_at < :now
                      AND we.spent_amount < we.amount
                      AND comp.id IS NULL
                    LIMIT 500
                    """
                ),
                {"now": now()},
            )
        ).all()
        for r in rows:
            await session.execute(
                text(
                    """
                    INSERT INTO wallet_entries
                        (id, wallet_id, amount, kind, source_type, source_id,
                         idempotency_key, created_at)
                    VALUES (gen_random_uuid(), :wid, -:amt, 'expire', 'expiration',
                            :src, 'expire:' || :src::text, :now)
                    """
                ),
                {"wid": r.wallet_id, "amt": r.remainder, "src": r.id, "now": now()},
            )
            await session.execute(
                text("UPDATE wallet_entries SET spent_amount = amount WHERE id = :id"),
                {"id": r.id},
            )
            await session.execute(
                text(
                    """
                    UPDATE cashback_wallets
                       SET balance = balance - :amt, version = version + 1
                     WHERE id = :wid
                    """
                ),
                {"amt": r.remainder, "wid": r.wallet_id},
            )
        await session.commit()
    if rows:
        log.info("wallet_entries_expired", count=len(rows))
    return len(rows)
