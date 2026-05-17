"""/start, contact-sharing, and the deferred-linking flow."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from app.bots.customer import keyboards, texts, views
from app.bots.tenant_resolver import resolve_tenant
from app.core.db import session_scope
from app.core.logging import get_logger
from app.core.phone import InvalidPhoneError
from app.domain import identity
from app.domain.dashboard import read_dashboard
from app.domain.errors import TelegramConflict
from app.domain.membership import get_active_membership
from app.models import Tenant

router = Router(name="customer.start")
log = get_logger("bot.customer.start")


def _telegram_lang(message: Message) -> str:
    code = message.from_user.language_code if message.from_user else None
    return texts.normalize_lang(code)


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    """First contact. We need the user's phone to identify them.

    If the user is already linked (`telegram_id` known), skip the prompt and
    show the dashboard right away.
    """
    if not message.from_user:
        return

    async with session_scope() as session:
        tenant_id = await resolve_tenant(session)
        existing = await identity.find_by_telegram(
            session,
            tenant_id=tenant_id,
            telegram_id=message.from_user.id,
        )

    if existing is not None:
        lang = texts.normalize_lang(existing.language)
        async with session_scope() as session:
            view = await read_dashboard(session, user_id=existing.id)
            tenant = (
                await session.execute(select(Tenant).where(Tenant.id == existing.tenant_id))
            ).scalar_one()
            membership = await get_active_membership(
                session, tenant_id=existing.tenant_id, user_id=existing.id
            )
        await message.answer(
            views.render_dashboard(
                view, currency=tenant.default_currency, lang=lang, membership=membership,
            ),
            parse_mode="HTML",
            reply_markup=keyboards.main_kb(lang),
        )
        return

    lang = _telegram_lang(message)
    await message.answer(
        texts.t("welcome", lang),
        reply_markup=keyboards.share_contact_kb(lang),
    )


@router.message(F.contact)
async def on_contact(message: Message) -> None:
    """Verified phone arrives via Telegram's request_contact button.

    Telegram only sends the user's *own* phone number when they tap the share
    button — this provides phone verification for free.
    """
    if not message.from_user or not message.contact:
        return

    lang = _telegram_lang(message)
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer(
            texts.t("wrong_contact", lang),
            reply_markup=keyboards.share_contact_kb(lang),
        )
        return

    raw_phone = contact.phone_number
    if not raw_phone:
        await message.answer(texts.t("invalid_phone", lang))
        return

    if not raw_phone.startswith("+"):
        raw_phone = "+" + raw_phone

    full_name = " ".join(
        x for x in (contact.first_name, contact.last_name) if x
    ) or message.from_user.full_name

    try:
        async with session_scope() as session:
            tenant_id = await resolve_tenant(session)
            result = await identity.link_telegram(
                session,
                tenant_id=tenant_id,
                phone=raw_phone,
                telegram_id=message.from_user.id,
                telegram_username=message.from_user.username,
                full_name=full_name,
                language=lang,
            )
            user = result.user
            view = await read_dashboard(session, user_id=user.id)
            tenant = (
                await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            ).scalar_one()
            membership = await get_active_membership(
                session, tenant_id=tenant_id, user_id=user.id
            )
    except TelegramConflict:
        await message.answer(texts.t("conflict", lang), reply_markup=keyboards.main_kb(lang))
        return
    except InvalidPhoneError:
        await message.answer(
            texts.t("invalid_phone", lang),
            reply_markup=keyboards.share_contact_kb(lang),
        )
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("link_failed", error=str(exc))
        await message.answer(texts.t("generic_error", lang))
        return

    # Re-read effective lang from the persisted user row.
    lang = texts.normalize_lang(user.language)
    greeting = (
        texts.t("linked_new", lang)
        if result.created
        else texts.t("linked_known", lang, name=user.full_name or "friend")
    )
    await message.answer(greeting, reply_markup=keyboards.main_kb(lang))
    await message.answer(
        views.render_dashboard(
            view, currency=tenant.default_currency, lang=lang, membership=membership,
        ),
        parse_mode="HTML",
        reply_markup=keyboards.main_kb(lang),
    )
