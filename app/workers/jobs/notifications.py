"""Schedule and send Telegram notifications for domain events.

For MVP we resolve a small static set of templates inline. V2 introduces
``notification_templates`` rows + per-tenant overrides + A/B variants.

Two correctness properties enforced here:

* **Idempotent enqueue.** Each ``notification_jobs`` row carries a
  ``dedup_key`` derived from the event payload. A partial unique index
  on ``(user_id, template_code, dedup_key)`` prevents the same event
  from creating two outbound messages if the outbox is replayed.
* **Quiet hours.** The publisher (``send_due``) compares the user's
  *local* time (``user.timezone`` falls back to the tenant default and
  finally to ``settings.default_timezone``) against
  ``user.notify_quiet_from/to``; jobs that would fire inside the window
  are deferred until the window ends.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.core.clock import now
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.domain import events as ev
from app.models import NotificationJob, User

log = get_logger("worker.notifications")


# ---- text templates ----------------------------------------------------------

TPL = {
    ev.EVT_PURCHASE_RECORDED: (
        "✅ +1 кофе. Прогресс: {stamps_total}/{stamps_required}"
    ),
    ev.EVT_FREE_UNLOCKED: (
        "🎁 Поздравляем! У тебя новый бесплатный кофе. Покажи код в кофейне."
    ),
    ev.EVT_PREPAID_CONSUMED: (
        "📦 Списан 1 кофе из пакета. Осталось: {remaining}."
    ),
    ev.EVT_PREPAID_EXHAUSTED: (
        "📦 Пакет закончился. Возьми ещё в кофейне!"
    ),
    ev.EVT_USER_LINKED: (
        "Привет! Карта успешно привязана 🎉"
    ),
    ev.EVT_TRANSACTION_REFUNDED: (
        "↩️ Транзакция возвращена. Эффекты в карте/пакете откатились."
    ),
}


# ---- enqueue -----------------------------------------------------------------


def _dedup_key(type_: str, payload: dict[str, Any]) -> str:
    """Stable hash of the payload — same event content ⇒ same key."""
    blob = json.dumps(
        {"t": type_, "p": payload}, sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


async def handle_event(
    type_: str,
    payload: dict[str, Any],
    *,
    tenant_id: uuid.UUID,
) -> None:
    """Translate a domain event into a queued notification_job row.

    Idempotent: if a job with the same ``(user_id, template_code,
    dedup_key)`` already exists (and was not cancelled), nothing is
    inserted.
    """
    template = TPL.get(type_)
    if template is None:
        return

    user_id = payload.get("user_id")
    if not user_id:
        return

    dedup = _dedup_key(type_, payload)

    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
        ).scalar_one_or_none()
        if not user or not user.telegram_id or not user.notify_opt_in:
            return

        # Use ON CONFLICT DO NOTHING via the partial unique index on
        # (user_id, template_code, dedup_key) — see migration 0004.
        from sqlalchemy.dialects.postgresql import insert

        stmt = (
            insert(NotificationJob)
            .values(
                tenant_id=tenant_id,
                user_id=user.id,
                template_code=type_,
                scheduled_at=now(),
                status="queued",
                context=payload,
                dedup_key=dedup,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "template_code", "dedup_key"],
                index_where="dedup_key IS NOT NULL AND status <> 'cancelled'",
            )
        )
        await session.execute(stmt)
        await session.commit()


# ---- publisher --------------------------------------------------------------


def _resolve_user_tz(user: User) -> ZoneInfo:
    """Pick the timezone we should evaluate quiet hours in."""
    candidates = (user.timezone, settings.default_timezone, "UTC")
    for tz in candidates:
        if not tz:
            continue
        try:
            return ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            continue
    return ZoneInfo("UTC")


def _quiet_window(user: User) -> tuple[time, time]:
    """Per-user override falls back to tenant-wide settings."""
    qf = user.notify_quiet_from or settings.quiet_hours_from
    qt = user.notify_quiet_to or settings.quiet_hours_to
    return qf, qt


def _is_in_quiet_window(local_now: datetime, qf: time, qt: time) -> bool:
    """Is ``local_now.time()`` inside the [qf, qt) window?

    Handles wrap-around (e.g. 22:00–08:00 spans midnight).
    """
    t = local_now.time()
    if qf == qt:
        return False
    if qf < qt:
        return qf <= t < qt
    return t >= qf or t < qt


def _next_send_after_quiet(local_now: datetime, qt: time) -> datetime:
    """Local datetime of the next moment ``qt`` happens at or after ``local_now``."""
    candidate = local_now.replace(
        hour=qt.hour, minute=qt.minute, second=0, microsecond=0
    )
    if candidate <= local_now:
        candidate = candidate + timedelta(days=1)
    return candidate


async def send_due(ctx: dict[str, Any]) -> int:  # noqa: ARG001
    """Pick queued notification jobs and send through the configured Telegram bot.

    Globally rate-limited via ``settings.telegram_global_rps``. Each job is
    quiet-hour-checked against the recipient's local time — if it falls in
    the window we push ``scheduled_at`` to the next wake-up and leave it
    ``queued``.
    """
    from aiogram import Bot
    from sqlalchemy import update

    if settings.customer_bot_token is None:
        return 0

    sent = 0
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(NotificationJob)
                .where(
                    NotificationJob.status == "queued",
                    NotificationJob.scheduled_at <= now(),
                )
                .order_by(NotificationJob.scheduled_at.asc())
                .limit(settings.telegram_global_rps)
            )
        ).scalars().all()

        if not rows:
            return 0

        bot = Bot(token=settings.customer_bot_token.get_secret_value())
        try:
            for job in rows:
                user = (
                    await session.execute(select(User).where(User.id == job.user_id))
                ).scalar_one_or_none()
                if not user or not user.telegram_id:
                    job.status = "skipped"
                    continue
                if not user.notify_opt_in:
                    job.status = "skipped"
                    continue

                # Quiet hours
                tz = _resolve_user_tz(user)
                local_now = now().astimezone(tz)
                qf, qt = _quiet_window(user)
                if _is_in_quiet_window(local_now, qf, qt):
                    deferred_local = _next_send_after_quiet(local_now, qt)
                    job.scheduled_at = deferred_local.astimezone(now().tzinfo)
                    continue

                template = TPL.get(job.template_code, "")
                if not template:
                    job.status = "skipped"
                    continue
                try:
                    text_ = template.format(**(job.context or {}))
                    await bot.send_message(user.telegram_id, text_)
                    job.status = "sent"
                    job.sent_at = now()
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    job.attempt += 1
                    job.status = "failed" if job.attempt >= 5 else "queued"
                    job.error = str(exc)[:500]
                    log.warning(
                        "notify_send_failed", job_id=str(job.id), error=str(exc)
                    )
        finally:
            await bot.session.close()
        await session.commit()

    if sent:
        log.info("notify_sent", count=sent)
    return sent
