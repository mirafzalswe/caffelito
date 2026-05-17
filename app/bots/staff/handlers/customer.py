"""Customer search + per-customer actions: add purchase, redeem free."""

from __future__ import annotations

import uuid
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bots.staff import keyboards
from app.bots.staff.customer_lookup import find_customer
from app.bots.staff.states import Work
from app.bots.tenant_resolver import resolve_tenant
from app.core.clock import now
from app.core.db import session_scope
from app.core.logging import get_logger
from app.core.phone import mask_phone
from app.core.security import random_token
from app.domain import redeem
from app.domain.dashboard import read_dashboard
from app.domain.errors import (
    CooldownActive,
    DomainError,
    FreeCoffeeExpired,
    FreeCoffeeNotAvailable,
)
from app.domain.loyalty_engine import record_purchase
from app.domain.schemas import PurchaseLine, PurchaseRequest
from app.models import Campaign, LoyaltyCard, PrepaidPackage, Product, User

router = Router(name="staff.customer")
log = get_logger("bot.staff.customer")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.message(Work.idle, F.text == "🔎 Найти клиента")
async def on_find(message: Message, state: FSMContext) -> None:
    await state.set_state(Work.finding_customer)
    await message.answer(
        "Введите телефон, последние 4+ цифры или 6-значный код клиента.",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(Work.finding_customer, F.text == "✖️ Отмена")
async def on_cancel_find(message: Message, state: FSMContext) -> None:
    await state.set_state(Work.idle)
    await message.answer("Отменено.", reply_markup=keyboards.main_menu_kb())


@router.message(Work.finding_customer, F.text)
async def on_find_input(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    async with session_scope() as session:
        tenant_id = await resolve_tenant(session)
        user = await find_customer(session, tenant_id=tenant_id, raw=raw)
        if user is None:
            await message.answer(
                "Клиент не найден. Попробуйте ввести точнее или предложите ему /start у клиентского бота.",
                reply_markup=keyboards.main_menu_kb(),
            )
            await state.set_state(Work.idle)
            return
        view = await read_dashboard(session, user_id=user.id)
        # Up to 6 fastest products to add — by base_price desc on the assumption
        # that "loyalty_eligible coffee" is the meaningful subset.
        prod_stmt = (
            select(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.is_active == True,  # noqa: E712
                Product.is_loyalty_eligible == True,  # noqa: E712
            )
            .order_by(Product.name)
            .limit(6)
        )
        products = list((await session.execute(prod_stmt)).scalars().all())

    data = await state.get_data()
    data["customer_id"] = str(user.id)
    await state.set_data(data)
    await state.set_state(Work.customer_active)

    summary = (
        f"<b>{user.full_name or 'Клиент'}</b> · {mask_phone(user.phone_e164)}\n"
        f"Карта: {view.stamps_total}/{view.stamps_required} · "
        f"🎁 {view.free_coffees_available} · "
        f"💰 {view.cashback_balance:.2f} · "
        f"📦 {view.prepaid_remaining}"
    )
    kb = keyboards.customer_actions_kb(
        user_id=user.id,
        has_free=view.free_coffees_available > 0,
        has_prepaid=view.prepaid_remaining > 0,
        products=[(p.id, _short_label(p), str(p.base_price)) for p in products],
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=keyboards.main_menu_kb())
    await message.answer("Действия:", reply_markup=kb)


def _short_label(p: Product) -> str:
    parts = [p.name]
    if p.size:
        parts.append(p.size)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Add product purchase (one-tap)
# ---------------------------------------------------------------------------


@router.callback_query(Work.customer_active, F.data.startswith("add:"))
async def on_add_product(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data or not query.message:
        return
    product_id = uuid.UUID(query.data.split(":", 1)[1])

    data = await state.get_data()
    customer_id = uuid.UUID(data["customer_id"])
    branch_id = uuid.UUID(data["branch_id"])
    staff_id = uuid.UUID(data["staff_id"])

    # Idempotency: a fresh UUID per tap. Telegram callback retries are rare,
    # but if the staff double-taps, we bind the same UUID to the click via
    # ``query.id`` so within ~60s the same press doesn't double-charge.
    crid = f"add:{query.id}"

    try:
        async with session_scope() as session:
            tenant_id = await resolve_tenant(session)
            req = PurchaseRequest(
                tenant_id=tenant_id,
                branch_id=branch_id,
                user_id=customer_id,
                staff_id=staff_id,
                lines=[PurchaseLine(product_id=product_id, qty=1, paid_with="money")],
                client_request_id=crid,
            )
            result = await record_purchase(session, request=req)
            view = await read_dashboard(session, user_id=customer_id)
    except DomainError as exc:
        await query.answer(f"❗ {exc}", show_alert=True)
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("add_failed", error=str(exc))
        await query.answer("Ошибка. Попробуйте ещё раз.", show_alert=True)
        return

    msg = (
        f"✅ +1 кофе · карта {view.stamps_total}/{view.stamps_required}"
        + (" 🎁" if result.free_coffees_unlocked else "")
    )
    await query.answer(msg)
    await query.message.answer(  # type: ignore[union-attr]
        f"<b>Готово.</b> {view.stamps_total}/{view.stamps_required}"
        + ("\n🎁 Открыт бесплатный кофе!" if result.free_coffees_unlocked else ""),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Free coffee redeem
# ---------------------------------------------------------------------------


@router.callback_query(Work.customer_active, F.data == "free")
async def on_free(query: CallbackQuery, state: FSMContext) -> None:
    """If the customer has free coffees on >1 card, ask which card to redeem from."""
    if not query.message:
        return
    data = await state.get_data()
    customer_id = uuid.UUID(data["customer_id"])

    async with session_scope() as session:
        stmt = (
            select(LoyaltyCard, Campaign.name)
            .join(Campaign, Campaign.id == LoyaltyCard.campaign_id)
            .where(
                LoyaltyCard.user_id == customer_id,
                LoyaltyCard.status == "complete",
            )
            .order_by(LoyaltyCard.completed_at.asc().nullslast())
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        await query.answer("У клиента нет доступного бесплатного кофе.", show_alert=True)
        return

    if len(rows) == 1:
        card = rows[0][0]
        data["pending_free_card_id"] = str(card.id)
        await state.set_data(data)
        await query.message.answer(  # type: ignore[union-attr]
            "Подтверждаем списание бесплатного кофе?",
            reply_markup=keyboards.confirm_kb(yes_data="free_yes", no_data="free_no"),
        )
        await query.answer()
        return

    cards = [(card.id, name or "Карта") for card, name in rows]
    await query.message.answer(  # type: ignore[union-attr]
        "У клиента бесплатный кофе на нескольких картах. С какой списать?",
        reply_markup=keyboards.free_picker_kb(cards),
    )
    await query.answer()


@router.callback_query(Work.customer_active, F.data.startswith("free_card:"))
async def on_free_pick(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data or not query.message:
        return
    card_id = uuid.UUID(query.data.split(":", 1)[1])
    data = await state.get_data()
    data["pending_free_card_id"] = str(card_id)
    await state.set_data(data)
    await query.message.answer(  # type: ignore[union-attr]
        "Подтверждаем списание бесплатного кофе с выбранной карты?",
        reply_markup=keyboards.confirm_kb(yes_data="free_yes", no_data="free_no"),
    )
    await query.answer()


@router.callback_query(Work.customer_active, F.data == "free_yes")
async def on_free_confirm(query: CallbackQuery, state: FSMContext) -> None:
    if not query.message:
        return
    data = await state.get_data()
    customer_id = uuid.UUID(data["customer_id"])
    branch_id = uuid.UUID(data["branch_id"])
    staff_id = uuid.UUID(data["staff_id"])
    pending = data.get("pending_free_card_id")
    card_id = uuid.UUID(pending) if pending else None
    crid = f"free:{query.id or random_token(8)}"

    try:
        async with session_scope() as session:
            tenant_id = await resolve_tenant(session)
            await redeem.redeem_free_coffee(
                session,
                tenant_id=tenant_id,
                branch_id=branch_id,
                user_id=customer_id,
                staff_id=staff_id,
                product_id=None,
                client_request_id=crid,
                card_id=card_id,
            )
            view = await read_dashboard(session, user_id=customer_id)
    except FreeCoffeeNotAvailable:
        await query.answer("У клиента нет доступного бесплатного кофе.", show_alert=True)
        return
    except FreeCoffeeExpired:
        await query.answer("Бесплатный кофе истёк по сроку.", show_alert=True)
        return
    except DomainError as exc:
        await query.answer(f"❗ {exc}", show_alert=True)
        return
    finally:
        if "pending_free_card_id" in data:
            data.pop("pending_free_card_id", None)
            await state.set_data(data)

    await query.answer("✅ Списано")
    await query.message.answer(  # type: ignore[union-attr]
        f"🎁 Готово. Бесплатных осталось: <b>{view.free_coffees_available}</b>",
        parse_mode="HTML",
    )


@router.callback_query(Work.customer_active, F.data == "free_no")
async def on_free_cancel(query: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if "pending_free_card_id" in data:
        data.pop("pending_free_card_id", None)
        await state.set_data(data)
    await query.answer("Отменено")


# ---------------------------------------------------------------------------
# Prepaid consume
# ---------------------------------------------------------------------------


@router.callback_query(Work.customer_active, F.data == "prepaid")
async def on_prepaid(query: CallbackQuery, state: FSMContext) -> None:
    """If the customer has >1 active package, ask the barista which one to debit."""
    if not query.message:
        return
    data = await state.get_data()
    customer_id = uuid.UUID(data["customer_id"])

    async with session_scope() as session:
        stmt = (
            select(PrepaidPackage, Campaign.name)
            .join(Campaign, Campaign.id == PrepaidPackage.campaign_id, isouter=True)
            .where(
                PrepaidPackage.user_id == customer_id,
                PrepaidPackage.status == "active",
                PrepaidPackage.qty_remaining > 0,
            )
            .order_by(PrepaidPackage.expires_at.asc().nullslast())
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        await query.answer("У клиента нет активного пакета.", show_alert=True)
        return

    if len(rows) == 1:
        pkg = rows[0][0]
        await _consume_prepaid(query, state, package_id=pkg.id)
        return

    packages = [
        (pkg.id, name or "Пакет", pkg.qty_remaining)
        for pkg, name in rows
    ]
    await query.message.answer(  # type: ignore[union-attr]
        "У клиента несколько активных пакетов. Какой списать?",
        reply_markup=keyboards.prepaid_picker_kb(packages),
    )
    await query.answer()


@router.callback_query(Work.customer_active, F.data.startswith("prep_pkg:"))
async def on_prepaid_pick(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data:
        return
    package_id = uuid.UUID(query.data.split(":", 1)[1])
    await _consume_prepaid(query, state, package_id=package_id)


@router.callback_query(Work.customer_active, F.data == "prep_cancel")
async def on_prepaid_cancel(query: CallbackQuery) -> None:
    await query.answer("Отменено")


async def _consume_prepaid(
    query: CallbackQuery, state: FSMContext, *, package_id: uuid.UUID
) -> None:
    from app.domain import prepaid as prepaid_svc

    data = await state.get_data()
    customer_id = uuid.UUID(data["customer_id"])
    branch_id = uuid.UUID(data["branch_id"])
    staff_id = uuid.UUID(data["staff_id"])
    crid = f"prep:{query.id or random_token(8)}"

    try:
        async with session_scope() as session:
            tenant_id = await resolve_tenant(session)
            await prepaid_svc.consume_one(
                session,
                tenant_id=tenant_id,
                branch_id=branch_id,
                user_id=customer_id,
                staff_id=staff_id,
                product_id=None,
                client_request_id=crid,
                package_id=package_id,
            )
            view = await read_dashboard(session, user_id=customer_id)
    except DomainError as exc:
        await query.answer(f"❗ {exc}", show_alert=True)
        return

    await query.answer("✅ Списано из пакета")
    if query.message:
        await query.message.answer(  # type: ignore[union-attr]
            f"📦 Остаток в пакете: <b>{view.prepaid_remaining}</b>",
            parse_mode="HTML",
        )


@router.callback_query(Work.customer_active, F.data == "done")
async def on_done(query: CallbackQuery, state: FSMContext) -> None:
    if not query.message:
        return
    await state.set_state(Work.idle)
    await query.message.answer(
        "Готово. Следующий клиент?",
        reply_markup=keyboards.main_menu_kb(),
    )
    await query.answer()


@router.callback_query(Work.customer_active, F.data == "code")
async def on_code(query: CallbackQuery) -> None:
    """Stub: ask the barista to type the 6-digit code via search.

    Real flow: barista taps "Принять код" → the staff bot asks for input
    in finding-customer mode and the same `find_customer` resolves it.
    """
    if not query.message:
        return
    await query.message.answer(
        "Попросите клиента показать код в его боте, затем нажмите «🔎 Найти клиента» "
        "и введите 6 цифр.",
    )
    await query.answer()
