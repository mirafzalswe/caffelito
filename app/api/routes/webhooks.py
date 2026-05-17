"""Telegram webhook receivers — production mode for both bots.

Local dev uses long-polling (see app.bots.{customer,staff}.__main__). When
TELEGRAM_*_WEBHOOK_URL is configured the bots register their endpoints here
on start and Telegram POSTs updates with the secret header.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.bots.customer.handlers import build_router as build_customer_router
from app.bots.staff.handlers import build_router as build_staff_router
from app.core.config import settings
from app.core.redis import get_redis

router = APIRouter(prefix="/webhook", tags=["telegram"])

_customer_bot: Bot | None = None
_customer_dp: Dispatcher | None = None
_staff_bot: Bot | None = None
_staff_dp: Dispatcher | None = None


def _customer() -> tuple[Bot, Dispatcher]:
    global _customer_bot, _customer_dp
    if _customer_bot is None:
        if settings.customer_bot_token is None:
            raise HTTPException(status_code=503, detail="customer bot not configured")
        _customer_bot = Bot(
            token=settings.customer_bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _customer_dp = Dispatcher(storage=RedisStorage(redis=get_redis()))
        _customer_dp.include_router(build_customer_router())
    assert _customer_dp is not None
    return _customer_bot, _customer_dp


def _staff() -> tuple[Bot, Dispatcher]:
    global _staff_bot, _staff_dp
    if _staff_bot is None:
        if settings.staff_bot_token is None:
            raise HTTPException(status_code=503, detail="staff bot not configured")
        _staff_bot = Bot(
            token=settings.staff_bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _staff_dp = Dispatcher(storage=RedisStorage(redis=get_redis()))
        _staff_dp.include_router(build_staff_router())
    assert _staff_dp is not None
    return _staff_bot, _staff_dp


def _check_secret(provided: str | None) -> None:
    expected = settings.telegram_webhook_secret.get_secret_value()
    if not provided or provided != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad webhook secret")


@router.post("/customer")
async def customer_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    _check_secret(x_telegram_bot_api_secret_token)
    bot, dp = _customer()
    payload = await request.json()
    update = Update.model_validate(payload)
    await dp.feed_update(bot, update)
    return {"ok": "ok"}


@router.post("/staff")
async def staff_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    _check_secret(x_telegram_bot_api_secret_token)
    bot, dp = _staff()
    payload = await request.json()
    update = Update.model_validate(payload)
    await dp.feed_update(bot, update)
    return {"ok": "ok"}
