"""Open a new prepaid package — wizard with qty + amount."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bots.staff import keyboards
from app.bots.staff.states import OpenPrepaid, Work
from app.bots.tenant_resolver import resolve_tenant
from app.core.config import settings
from app.core.db import session_scope
from app.core.security import random_token
from app.domain import prepaid as prepaid_svc
from app.domain.errors import DomainError

router = Router(name="staff.prepaid")


@router.message(Work.customer_active, F.text == "📦 Открыть пакет")
async def on_open_start(message: Message, state: FSMContext) -> None:
    await state.set_state(OpenPrepaid.waiting_qty)
    await message.answer(
        "Сколько кофе в пакете? (целое число, например 10)",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(OpenPrepaid.waiting_qty, F.text)
async def on_qty(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    if txt == "✖️ Отмена":
        await state.set_state(Work.customer_active)
        await message.answer("Отменено.", reply_markup=keyboards.main_menu_kb())
        return
    if not txt.isdigit() or int(txt) <= 0:
        await message.answer("Введите целое положительное число.")
        return
    data = await state.get_data()
    data["prepaid_qty"] = int(txt)
    await state.set_data(data)
    await state.set_state(OpenPrepaid.waiting_amount)
    await message.answer("Какая сумма оплачена? (например 35.00)")


@router.message(OpenPrepaid.waiting_amount, F.text)
async def on_amount(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip().replace(",", ".")
    if txt == "✖️ Отмена":
        await state.set_state(Work.customer_active)
        await message.answer("Отменено.", reply_markup=keyboards.main_menu_kb())
        return
    try:
        amount = Decimal(txt)
        if amount < 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("Введите неотрицательное число (например 35.00).")
        return

    data = await state.get_data()
    qty = int(data["prepaid_qty"])
    customer_id = uuid.UUID(data["customer_id"])
    branch_id = uuid.UUID(data["branch_id"])
    staff_id = uuid.UUID(data["staff_id"])
    crid = f"open:{random_token(10)}"

    try:
        async with session_scope() as session:
            tenant_id = await resolve_tenant(session)
            await prepaid_svc.open_package(
                session,
                tenant_id=tenant_id,
                branch_id=branch_id,
                user_id=customer_id,
                staff_id=staff_id,
                qty=qty,
                amount_paid=amount,
                currency=settings.default_currency,
                product_scope={"all_loyalty_eligible": True},
                client_request_id=crid,
            )
    except DomainError as exc:
        await message.answer(f"❗ {exc}")
        await state.set_state(Work.customer_active)
        return
    except Exception:  # noqa: BLE001
        await message.answer("Ошибка при открытии пакета. Попробуйте ещё раз.")
        await state.set_state(Work.customer_active)
        return

    await message.answer(
        f"✅ Пакет на {qty} кофе открыт. Оплачено {amount} {settings.default_currency}.",
        reply_markup=keyboards.main_menu_kb(),
    )
    await state.set_state(Work.customer_active)
