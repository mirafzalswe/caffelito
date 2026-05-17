"""Push messages to customers via the customer-bot.

Called fire-and-forget from admin routes whenever something happens to the
customer's account (purchase, bonus grant, VIP activation, redeem). The user's
``language`` is read from the DB to pick the right copy.

The bot session is opened per-call and closed in ``finally`` so we don't leak
HTTPX clients. Errors (user blocked the bot, network glitch) are swallowed —
notifications are best-effort, never block the admin's request.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select

from app.bots.customer import texts
from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.models import User

log = get_logger("domain.customer_notify")


async def _send(user_id: uuid.UUID, key: str, **fmt) -> None:
    """Lookup the user, translate ``key`` into their language, send via bot."""
    if settings.customer_bot_token is None:
        return  # bot not configured — skip silently

    async with session_scope() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None or not user.telegram_id:
            return
        lang = texts.normalize_lang(user.language)
        telegram_id = user.telegram_id

    text = texts.t(key, lang, **fmt)

    bot = Bot(
        token=settings.customer_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(telegram_id, text)
    except Exception as exc:  # noqa: BLE001
        log.info("notify_failed", user=str(user_id), key=key, error=str(exc)[:120])
    finally:
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001
            pass


async def notify_purchase(
    user_id: uuid.UUID,
    *,
    stamps_added: int,
    cashback_earned: Decimal,
    free_coffees_unlocked: int,
    currency: str,
    vip_charged: Decimal | None = None,
    vip_balance_remaining: Decimal | None = None,
) -> None:
    """Compose and send the per-purchase summary."""
    lines: list[str] = []
    if vip_charged is not None and vip_balance_remaining is not None:
        lines.append(("notify.vip_charged", {
            "charged": f"{vip_charged:.2f}",
            "balance": f"{vip_balance_remaining:.2f}",
            "currency": currency,
        }))
    if stamps_added > 0:
        lines.append(("notify.stamps", {"n": stamps_added}))
    if cashback_earned > 0:
        lines.append(("notify.cashback", {
            "amount": f"{cashback_earned:.2f}",
            "currency": currency,
        }))
    if free_coffees_unlocked > 0:
        lines.append(("notify.free_unlocked", {"n": free_coffees_unlocked}))

    if not lines:
        return  # nothing worth a push

    # Pick the user lang ONCE so we batch the translations inside _send_html.
    if settings.customer_bot_token is None:
        return
    async with session_scope() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None or not user.telegram_id:
            return
        lang = texts.normalize_lang(user.language)
        telegram_id = user.telegram_id

    body_parts = [texts.t("notify.purchase_header", lang)]
    for key, fmt in lines:
        body_parts.append(texts.t(key, lang, **fmt))
    body = "\n".join(body_parts)

    bot = Bot(
        token=settings.customer_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(telegram_id, body)
    except Exception as exc:  # noqa: BLE001
        log.info("notify_purchase_failed", user=str(user_id), error=str(exc)[:120])
    finally:
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001
            pass


async def notify_vip_activated(
    user_id: uuid.UUID,
    *,
    discount_percent: int,
    balance: Decimal,
    currency: str,
) -> None:
    await _send(
        user_id, "notify.vip_activated",
        pct=discount_percent,
        balance=f"{balance:.2f}",
        currency=currency,
    )


async def notify_free_redeemed(user_id: uuid.UUID, *, remaining: int) -> None:
    await _send(user_id, "notify.free_redeemed", n=remaining)


async def notify_bonus_granted(
    user_id: uuid.UUID,
    *,
    kind: str,            # 'free_coffee' | 'stamps' | 'cashback'
    qty: int,
    amount: Decimal | None = None,
    currency: str = "UZS",
) -> None:
    if kind == "free_coffee":
        await _send(user_id, "notify.bonus_free", n=qty)
    elif kind == "stamps":
        await _send(user_id, "notify.bonus_stamps", n=qty)
    elif kind == "cashback" and amount is not None:
        await _send(
            user_id, "notify.bonus_cashback",
            amount=f"{amount:.2f}", currency=currency,
        )
