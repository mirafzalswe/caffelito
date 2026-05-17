"""Language switcher: /lang command + 🌐 button + inline RU/UZ picker."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bots.customer import keyboards, texts, views
from app.bots.customer.handlers._common import require_user_or_prompt
from app.bots.tenant_resolver import resolve_tenant
from app.core.db import session_scope
from app.core.logging import get_logger
from app.domain import identity
from app.domain.dashboard import read_dashboard
from app.domain.membership import get_active_membership
from app.models import Tenant, User

router = Router(name="customer.lang")
log = get_logger("bot.customer.lang")


@router.message(F.text.in_(texts.btn_set("btn.lang")))
@router.message(Command("lang"))
async def on_lang_open(message: Message) -> None:
    # The choose-prompt is bilingual on purpose so it makes sense either way.
    await message.answer(
        texts.t("lang.choose", "ru"),
        reply_markup=keyboards.lang_picker_kb(),
    )


@router.callback_query(F.data.startswith("lang:"))
async def on_lang_pick(query: CallbackQuery) -> None:
    """Persist users.language and re-render the dashboard in the chosen lang.

    The customer is identified by ``query.from_user`` (the real user who
    clicked the inline button) — NOT ``query.message.from_user`` which is the
    bot account that posted the keyboard.
    """
    if not query.data or not query.from_user:
        return
    new_lang = texts.normalize_lang(query.data.split(":", 1)[1])

    async with session_scope() as session:
        tenant_id = await resolve_tenant(session)
        user = await identity.find_by_telegram(
            session, tenant_id=tenant_id, telegram_id=query.from_user.id
        )
        if user is None:
            await query.answer()
            if query.message:
                await query.message.answer(  # type: ignore[union-attr]
                    texts.t("welcome", new_lang),
                    reply_markup=keyboards.share_contact_kb(new_lang),
                )
            return

        await session.execute(
            User.__table__.update()
            .where(User.id == user.id)
            .values(language=new_lang)
        )
        view = await read_dashboard(session, user_id=user.id)
        tenant = (
            await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        ).scalar_one()
        currency = tenant.default_currency
        membership = await get_active_membership(
            session, tenant_id=user.tenant_id, user_id=user.id
        )

    await query.answer(texts.t("lang.saved", new_lang))
    if query.message:
        await query.message.answer(  # type: ignore[union-attr]
            texts.t("lang.saved", new_lang),
            reply_markup=keyboards.main_kb(new_lang),
        )
        await query.message.answer(  # type: ignore[union-attr]
            views.render_dashboard(
                view, currency=currency, lang=new_lang, membership=membership,
            ),
            parse_mode="HTML",
            reply_markup=keyboards.main_kb(new_lang),
        )
