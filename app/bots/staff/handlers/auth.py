"""PIN-based staff auth + branch selection."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bots.staff import keyboards
from app.bots.staff.auth_service import (
    find_staff_by_pin,
    find_staff_by_telegram,
    list_staff_branches,
)
from app.bots.staff.states import Auth, Work
from app.bots.tenant_resolver import resolve_tenant
from app.core.db import session_scope
from app.core.logging import get_logger

router = Router(name="staff.auth")
log = get_logger("bot.staff.auth")


@router.message(Command("start"))
async def on_start(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    async with session_scope() as session:
        tenant_id = await resolve_tenant(session)
        staff = await find_staff_by_telegram(
            session, tenant_id=tenant_id, telegram_id=message.from_user.id
        )
        branches = await list_staff_branches(session, staff_id=staff.id) if staff else []

    if staff is None:
        await state.set_state(Auth.waiting_pin)
        await message.answer(
            "Введите PIN сотрудника (4–6 цифр).",
            reply_markup=keyboards.cancel_kb(),
        )
        return

    if not branches:
        await message.answer(
            "К вам не привязана ни одна точка. Обратитесь к менеджеру.",
        )
        return

    if len(branches) == 1:
        b = branches[0]
        await state.set_data({"staff_id": str(staff.id), "branch_id": str(b.id)})
        await state.set_state(Work.idle)
        await message.answer(
            f"Смена открыта: <b>{b.name}</b>",
            reply_markup=keyboards.main_menu_kb(),
            parse_mode="HTML",
        )
        return

    await state.set_data({"staff_id": str(staff.id)})
    await state.set_state(Auth.waiting_branch)
    await message.answer(
        "Выберите точку для смены:",
        reply_markup=keyboards.branches_kb([(b.id, b.name) for b in branches]),
    )


@router.message(Auth.waiting_pin, F.text)
async def on_pin(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    pin = (message.text or "").strip()
    if pin == "✖️ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=keyboards.remove_kb())
        return
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        await message.answer("PIN должен быть 4–6 цифр. Попробуйте ещё раз.")
        return

    async with session_scope() as session:
        tenant_id = await resolve_tenant(session)
        staff = await find_staff_by_pin(session, tenant_id=tenant_id, pin=pin)
        if staff is None:
            await message.answer("PIN не подходит. Попробуйте ещё раз.")
            return
        # Bind telegram_id to this staff record
        if staff.telegram_id is None:
            staff.telegram_id = message.from_user.id
            await session.flush()
        branches = await list_staff_branches(session, staff_id=staff.id)

    if not branches:
        await state.clear()
        await message.answer(
            "К вашему профилю не привязана ни одна точка. Обратитесь к менеджеру.",
            reply_markup=keyboards.remove_kb(),
        )
        return

    if len(branches) == 1:
        b = branches[0]
        await state.set_data({"staff_id": str(staff.id), "branch_id": str(b.id)})
        await state.set_state(Work.idle)
        await message.answer(
            f"Смена открыта: <b>{b.name}</b>",
            reply_markup=keyboards.main_menu_kb(),
            parse_mode="HTML",
        )
        return

    await state.set_data({"staff_id": str(staff.id)})
    await state.set_state(Auth.waiting_branch)
    await message.answer(
        "Выберите точку для смены:",
        reply_markup=keyboards.branches_kb([(b.id, b.name) for b in branches]),
    )


@router.callback_query(Auth.waiting_branch, F.data.startswith("branch:"))
async def on_branch_pick(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data:
        return
    bid = query.data.split(":", 1)[1]
    data = await state.get_data()
    data["branch_id"] = bid
    await state.set_data(data)
    await state.set_state(Work.idle)
    await query.message.answer(  # type: ignore[union-attr]
        "Смена открыта. Что делаем?",
        reply_markup=keyboards.main_menu_kb(),
    )
    await query.answer()


@router.message(F.text == "🚪 Конец смены")
async def on_logout(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Смена закрыта. Возвращайтесь!",
        reply_markup=keyboards.remove_kb(),
    )
