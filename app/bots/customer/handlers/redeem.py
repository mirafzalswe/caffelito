"""Show redeem code so the barista can complete a free-coffee redeem."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bots.customer import keyboards, texts
from app.bots.customer.handlers._common import require_user_or_prompt
from app.core.db import session_scope
from app.domain.dashboard import read_dashboard
from app.domain.redeem_code import issue_code

router = Router(name="customer.redeem")


def _progress_bar(filled: int, required: int) -> str:
    filled = max(0, min(filled, required))
    return texts.PROGRESS_FILLED * filled + texts.PROGRESS_EMPTY * max(0, required - filled)


def _no_free_message(view, lang: str) -> str:
    """Encouraging copy when the customer has no free coffee yet."""
    if view.stamps_required <= 0:
        return f"{texts.t('no_free.no_card_head', lang)}\n\n{texts.t('no_free.no_card_body', lang)}"

    left = max(0, view.stamps_required - view.stamps_total)
    bar = _progress_bar(view.stamps_total, view.stamps_required)

    if left == 1:
        head = texts.t("no_free.one", lang)
        tail = texts.t("no_free.one_tail", lang)
    elif left <= 3:
        head = texts.t("no_free.few", lang, n=left)
        tail = texts.t("no_free.few_tail", lang)
    else:
        head = texts.t("no_free.many", lang, n=left)
        tail = texts.t("no_free.many_tail", lang)

    return (
        f"{head}\n\n"
        f"{bar}\n"
        f"<b>{view.stamps_total}</b> / {view.stamps_required}\n\n"
        f"{tail}"
    )


@router.message(F.text.in_(texts.btn_set("btn.redeem")))
async def on_redeem(message: Message) -> None:
    user = await require_user_or_prompt(message)
    if not user:
        return
    lang = texts.normalize_lang(user.language)
    async with session_scope() as session:
        view = await read_dashboard(session, user_id=user.id)
    if view.free_coffees_available <= 0:
        await message.answer(
            _no_free_message(view, lang),
            parse_mode="HTML",
            reply_markup=keyboards.main_kb(lang),
        )
        return

    code = await issue_code(
        user_id=user.id,
        tenant_id=user.tenant_id,
        intent="free",
    )
    await message.answer(
        texts.t("redeem.have", lang, n=view.free_coffees_available)
        + "\n\n"
        + texts.t("redeem.code", lang, code=code),
        parse_mode="HTML",
        reply_markup=keyboards.main_kb(lang),
    )
