"""Entry point for `python -m app.bots.customer` (long-polling local mode)."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.bots.customer.handlers import build_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import get_redis


async def main() -> None:
    setup_logging()
    log = get_logger("bot.customer")

    if settings.customer_bot_token is None:
        raise SystemExit("CUSTOMER_BOT_TOKEN is not set in .env")

    bot = Bot(
        token=settings.customer_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage(redis=get_redis())
    dp = Dispatcher(storage=storage)
    dp.include_router(build_router())

    me = await bot.get_me()
    log.info("customer_bot_start", username=me.username)

    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
