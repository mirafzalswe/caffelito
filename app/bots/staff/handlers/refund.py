"""Refund flow: find tx → ask reason → confirm → apply via domain.refund."""

from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import String, cast, select

from app.bots.staff import keyboards
from app.bots.staff.states import Refund, Work
from app.bots.tenant_resolver import resolve_tenant
from app.core.db import session_scope
from app.core.logging import get_logger
from app.core.security import random_token
from app.domain import refund as refund_svc
from app.domain.errors import DomainError, RefundNotAllowed, TransactionNotFound
from app.models import Transaction

router = Router(name="staff.refund")
log = get_logger("bot.staff.refund")


_REFUND_REASONS = {
    "wrong_order": "Ошибка в заказе",
    "customer_changed_mind": "Клиент передумал",
    "barista_mistake": "Ошибка бариста",
    "duplicate_charge": "Двойное списание",
    "other": "Другое",
}


@router.message(Work.idle, F.text == "↩️ Возврат")
async def on_refund_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Refund.waiting_tx)
    await message.answer(
        "Введите ID транзакции (полный UUID или последние 8 символов).\n"
        "Например: <code>e32266f5</code>",
        parse_mode="HTML",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(Refund.waiting_tx, F.text == "✖️ Отмена")
async def on_cancel_tx(message: Message, state: FSMContext) -> None:
    await state.set_state(Work.idle)
    await message.answer("Отменено.", reply_markup=keyboards.main_menu_kb())


@router.message(Refund.waiting_tx, F.text)
async def on_tx_input(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().lower().replace(" ", "")
    if not raw:
        return

    async with session_scope() as session:
        tenant_id = await resolve_tenant(session)
        tx = await _resolve_transaction(session, tenant_id=tenant_id, raw=raw)
        if tx is None:
            await message.answer(
                "Транзакция не найдена. Проверьте ID и повторите ввод.",
            )
            return
        if tx.type not in refund_svc.REFUNDABLE_TYPES:
            await state.set_state(Work.idle)
            await message.answer(
                f"Транзакция типа <b>{tx.type}</b> не подлежит возврату.",
                parse_mode="HTML",
                reply_markup=keyboards.main_menu_kb(),
            )
            return
        if tx.status != "committed":
            await state.set_state(Work.idle)
            await message.answer(
                f"Транзакция уже в статусе <b>{tx.status}</b> — возврат не нужен.",
                parse_mode="HTML",
                reply_markup=keyboards.main_menu_kb(),
            )
            return

    data = await state.get_data()
    data["refund_tx_id"] = str(tx.id)
    await state.set_data(data)
    await state.set_state(Refund.waiting_reason)
    await message.answer(
        f"Возврат транзакции <code>{str(tx.id)[:8]}</code> "
        f"на сумму <b>{tx.total_amount} {tx.currency}</b>.\n\n"
        "Выберите причину:",
        parse_mode="HTML",
        reply_markup=_reason_kb(),
    )


@router.callback_query(Refund.waiting_reason, F.data.startswith("rfn:"))
async def on_reason_pick(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data or not query.message:
        return
    code = query.data.split(":", 1)[1]
    reason = _REFUND_REASONS.get(code, "Другое")

    data = await state.get_data()
    data["refund_reason"] = reason
    await state.set_data(data)
    await state.set_state(Refund.waiting_confirm)

    tx_short = str(data.get("refund_tx_id", ""))[:8]
    await query.message.answer(  # type: ignore[union-attr]
        f"Подтвердить возврат <code>{tx_short}</code>?\n"
        f"Причина: <i>{reason}</i>",
        parse_mode="HTML",
        reply_markup=keyboards.confirm_kb(yes_data="rfn_yes", no_data="rfn_no"),
    )
    await query.answer()


@router.callback_query(Refund.waiting_confirm, F.data == "rfn_yes")
async def on_confirm_yes(query: CallbackQuery, state: FSMContext) -> None:
    if not query.message:
        return
    data = await state.get_data()
    tx_id = uuid.UUID(data["refund_tx_id"])
    branch_id = uuid.UUID(data["branch_id"])
    staff_id = uuid.UUID(data["staff_id"])
    reason = data.get("refund_reason", "")
    crid = f"refund:{query.id or random_token(8)}"

    try:
        async with session_scope() as session:
            tenant_id = await resolve_tenant(session)
            refund_tx = await refund_svc.refund_transaction(
                session,
                tenant_id=tenant_id,
                branch_id=branch_id,
                staff_id=staff_id,
                transaction_id=tx_id,
                reason=reason,
                client_request_id=crid,
            )
    except TransactionNotFound:
        await query.answer("Транзакция не найдена.", show_alert=True)
        await state.set_state(Work.idle)
        return
    except RefundNotAllowed as exc:
        await query.answer(str(exc), show_alert=True)
        await state.set_state(Work.idle)
        return
    except DomainError as exc:
        await query.answer(f"❗ {exc}", show_alert=True)
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("refund_failed", error=str(exc))
        await query.answer("Ошибка возврата. Попробуйте ещё раз.", show_alert=True)
        return

    await query.answer("✅ Возврат проведён")
    await query.message.answer(  # type: ignore[union-attr]
        f"✅ Возврат проведён. Транзакция возврата: <code>{str(refund_tx)[:8]}</code>",
        parse_mode="HTML",
        reply_markup=keyboards.main_menu_kb(),
    )
    await state.set_state(Work.idle)


@router.callback_query(Refund.waiting_confirm, F.data == "rfn_no")
async def on_confirm_no(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Work.idle)
    await query.answer("Отменено")
    if query.message:
        await query.message.answer(  # type: ignore[union-attr]
            "Возврат отменён.", reply_markup=keyboards.main_menu_kb()
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_transaction(
    session,  # type: ignore[no-untyped-def]
    *,
    tenant_id: uuid.UUID,
    raw: str,
) -> Transaction | None:
    """Locate a transaction by full UUID or by the last N hex characters
    of its id. Returns the most recent match if multiple exist."""
    raw = raw.strip().lower()
    try:
        tx_id = uuid.UUID(raw)
        return (
            await session.execute(
                select(Transaction).where(
                    Transaction.id == tx_id, Transaction.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
    except ValueError:
        pass

    # Treat raw as a suffix of the UUID's hex form (with or without dashes).
    suffix = raw.replace("-", "")
    if len(suffix) < 4:
        return None

    stmt = (
        select(Transaction)
        .where(
            Transaction.tenant_id == tenant_id,
            cast(Transaction.id, String).ilike(f"%{suffix}"),
        )
        .order_by(Transaction.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _reason_kb():  # type: ignore[no-untyped-def]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"rfn:{code}")]
        for code, label in _REFUND_REASONS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
