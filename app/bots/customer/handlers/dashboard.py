"""Home / refresh handler."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select

from app.bots.customer import keyboards, texts, views
from app.bots.customer.handlers._common import require_user_or_prompt
from app.core.db import session_scope
from app.domain.dashboard import read_dashboard
from app.domain.membership import get_active_membership
from app.models import Tenant

router = Router(name="customer.dashboard")


@router.message(F.text.in_(texts.btn_set("btn.refresh")))
async def on_refresh(message: Message) -> None:
    user = await require_user_or_prompt(message)
    if not user:
        return
    lang = texts.normalize_lang(user.language)
    async with session_scope() as session:
        view = await read_dashboard(session, user_id=user.id)
        tenant = (
            await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        ).scalar_one()
        membership = await get_active_membership(
            session, tenant_id=user.tenant_id, user_id=user.id
        )
    await message.answer(
        views.render_dashboard(
            view, currency=tenant.default_currency, lang=lang, membership=membership,
        ),
        parse_mode="HTML",
        reply_markup=keyboards.main_kb(lang),
    )
