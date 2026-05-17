"""Owner-driven broadcasts: send a text/photo/video to every linked customer.

Public entry point: ``dispatch(broadcast_id)``. The function loads the
broadcast row, builds a Telegram ``Bot`` using ``customer_bot_token`` and
walks all eligible users in batches. Counters are persisted as the run
progresses so the admin UI can show live progress.

This is intentionally simple — no Celery/arq for MVP. The admin route schedules
it via ``asyncio.create_task`` and returns immediately so the request doesn't
block.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from sqlalchemy import func, select, update

from app.core.clock import now
from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models import Broadcast, User

log = get_logger("domain.broadcast")

# Telegram limits: ~30 msg/sec to different chats. We stay conservative at 20.
_THROTTLE_SECONDS = 0.05


async def dispatch(broadcast_id: uuid.UUID) -> None:
    """Send the broadcast to every linked customer of the tenant.

    Errors per-recipient (eg. user blocked the bot) are counted as ``failed``
    and do not abort the run. Fatal errors mark the broadcast as ``failed``.
    """
    if settings.customer_bot_token is None:
        await _mark_failed(broadcast_id, "CUSTOMER_BOT_TOKEN is not set")
        return

    async with session_scope() as session:
        bcast = (await session.execute(
            select(Broadcast).where(Broadcast.id == broadcast_id)
        )).scalar_one_or_none()
        if bcast is None or bcast.status != "sending":
            log.warning("broadcast_not_ready", id=str(broadcast_id))
            return

        recipients = (await session.execute(
            select(User.id, User.telegram_id).where(
                User.tenant_id == bcast.tenant_id,
                User.telegram_id.is_not(None),
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )).all()
        total = len(recipients)
        await session.execute(
            update(Broadcast).where(Broadcast.id == broadcast_id)
            .values(total_recipients=total)
        )

    if total == 0:
        await _mark_done(broadcast_id, sent=0, failed=0)
        return

    bot = Bot(
        token=settings.customer_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    sent = 0
    failed = 0
    try:
        media_path = Path(bcast.media_path) if bcast.media_path else None
        if media_path and not media_path.exists():
            media_path = None  # file deleted from disk; fall back to text-only

        for _, telegram_id in recipients:
            try:
                if media_path and bcast.media_type == "photo":
                    await bot.send_photo(
                        telegram_id,
                        photo=FSInputFile(str(media_path)),
                        caption=bcast.body or None,
                    )
                elif media_path and bcast.media_type == "video":
                    await bot.send_video(
                        telegram_id,
                        video=FSInputFile(str(media_path)),
                        caption=bcast.body or None,
                    )
                else:
                    await bot.send_message(telegram_id, bcast.body)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.info(
                    "broadcast_send_failed",
                    broadcast=str(broadcast_id),
                    telegram_id=telegram_id,
                    error=str(exc)[:200],
                )

            # Persist progress every ~25 sends so the UI sees live counters.
            if (sent + failed) % 25 == 0:
                async with session_scope() as session:
                    await session.execute(
                        update(Broadcast).where(Broadcast.id == broadcast_id)
                        .values(sent_count=sent, failed_count=failed)
                    )

            await asyncio.sleep(_THROTTLE_SECONDS)

        await _mark_done(broadcast_id, sent=sent, failed=failed)
    except Exception as exc:  # noqa: BLE001
        log.exception("broadcast_fatal", id=str(broadcast_id))
        await _mark_failed(broadcast_id, str(exc)[:500])
    finally:
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001
            pass


async def _mark_done(broadcast_id: uuid.UUID, *, sent: int, failed: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(Broadcast).where(Broadcast.id == broadcast_id).values(
                status="done",
                sent_count=sent,
                failed_count=failed,
                sent_at=now(),
            )
        )


async def _mark_failed(broadcast_id: uuid.UUID, error: str) -> None:
    async with session_scope() as session:
        await session.execute(
            update(Broadcast).where(Broadcast.id == broadcast_id).values(
                status="failed", error=error, sent_at=now(),
            )
        )


async def count_eligible_recipients(session, *, tenant_id: uuid.UUID) -> int:
    """Live count of customers who will receive the next broadcast."""
    return (await session.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.telegram_id.is_not(None),
            User.status == "active",
            User.deleted_at.is_(None),
        )
    )).scalar_one()
