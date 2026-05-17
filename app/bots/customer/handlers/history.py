"""Recent transactions list."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bots.customer import keyboards, texts
from app.bots.customer.handlers._common import require_user_or_prompt
from app.core.db import session_scope
from app.domain.dashboard import recent_transactions

router = Router(name="customer.history")

_TYPE = {
    "purchase":        ("🛒", "tx.purchase",     "−"),
    "redeem_free":     ("🎁", "tx.redeem_free",  ""),
    "prepaid_consume": ("📦", "tx.prepaid",      ""),
    "manual_grant":    ("✨", "tx.grant",        "+"),
    "refund":          ("↩️", "tx.refund",       "+"),
}


@router.message(F.text.in_(texts.btn_set("btn.history")))
async def on_history(message: Message) -> None:
    user = await require_user_or_prompt(message)
    if not user:
        return
    lang = texts.normalize_lang(user.language)
    async with session_scope() as session:
        rows = await recent_transactions(session, user_id=user.id, limit=15)

    if not rows:
        await message.answer(texts.t("history.empty", lang), reply_markup=keyboards.main_kb(lang))
        return

    lines = [texts.t("history.header", lang)]
    for tx in rows:
        icon, key, sign = _TYPE.get(tx.type, ("•", None, ""))
        label = texts.t(key, lang) if key else tx.type
        when = tx.created_at.strftime("%d.%m %H:%M")
        if tx.total_amount and tx.total_amount > 0:
            amount = f"{sign}{tx.total_amount:.0f} {tx.currency}"
        else:
            amount = "—"
        lines.append(f"{icon} <b>{label}</b> · {when} · {amount}")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboards.main_kb(lang))
