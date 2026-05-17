"""Outbox publisher — drains unpublished events into per-event handlers.

Strategy:
* SELECT FOR UPDATE SKIP LOCKED a small batch.
* Mark each as published_at = now() inside the same DB tx after the side-effect.
* On crash mid-handle, the row stays unpublished and is retried — handlers must
  be idempotent (notification jobs use template_code+context fingerprint).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.clock import now
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.domain import events as ev
from app.workers.jobs.notifications import handle_event as notify_handle

log = get_logger("worker.outbox")

BATCH = 50


async def drain_outbox(ctx: dict[str, Any]) -> int:  # noqa: ARG001
    """Process up to BATCH unpublished outbox events.

    Returns number of events processed (caller schedules itself again).
    """
    processed = 0
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, tenant_id, aggregate_type, aggregate_id, type, payload
                    FROM outbox_events
                    WHERE published_at IS NULL
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT :batch
                    """
                ),
                {"batch": BATCH},
            )
        ).all()

        for row in rows:
            try:
                await _dispatch(row.type, dict(row.payload), tenant_id=row.tenant_id)
                await session.execute(
                    text(
                        "UPDATE outbox_events SET published_at = :ts WHERE id = :id"
                    ),
                    {"ts": now(), "id": row.id},
                )
                processed += 1
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "outbox_dispatch_failed",
                    outbox_id=row.id,
                    type=row.type,
                    error=str(exc),
                )
        await session.commit()
    if processed:
        log.info("outbox_drained", processed=processed)
    return processed


async def _dispatch(type_: str, payload: dict[str, Any], *, tenant_id) -> None:
    if type_ in {
        ev.EVT_FREE_UNLOCKED,
        ev.EVT_PURCHASE_RECORDED,
        ev.EVT_PREPAID_CONSUMED,
        ev.EVT_PREPAID_EXHAUSTED,
        ev.EVT_USER_LINKED,
        ev.EVT_USER_CREATED,
    }:
        await notify_handle(type_, payload, tenant_id=tenant_id)
