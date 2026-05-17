"""Shared helpers for customer bot handlers."""

from __future__ import annotations

import uuid

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.customer import keyboards, texts
from app.bots.tenant_resolver import resolve_tenant
from app.domain import identity
from app.models import User


async def resolve_user(
    session: AsyncSession,
    message: Message,
) -> tuple[uuid.UUID, User | None]:
    """Find tenant + the linked customer for this Telegram user (or None)."""
    tenant_id = await resolve_tenant(session)
    if not message.from_user:
        return tenant_id, None
    user = await identity.find_by_telegram(
        session, tenant_id=tenant_id, telegram_id=message.from_user.id
    )
    return tenant_id, user


async def require_user_or_prompt(message: Message) -> User | None:
    from app.core.db import session_scope

    async with session_scope() as session:
        _, user = await resolve_user(session, message)
    if user is None:
        tg_lang = message.from_user.language_code if message.from_user else None
        lang = texts.normalize_lang(tg_lang)
        await message.answer(
            texts.t("welcome", lang),
            reply_markup=keyboards.share_contact_kb(lang),
        )
        return None
    return user
