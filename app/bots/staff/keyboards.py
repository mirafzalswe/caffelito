"""Keyboards for the staff bot."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Найти клиента")],
            [KeyboardButton(text="📦 Открыть пакет"), KeyboardButton(text="↩️ Возврат")],
            [KeyboardButton(text="🚪 Конец смены")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✖️ Отмена")]],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def branches_kb(rows: Iterable[tuple[uuid.UUID, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"branch:{bid}")]
            for bid, name in rows
        ]
    )


def customer_actions_kb(
    *,
    user_id: uuid.UUID,
    has_free: bool,
    has_prepaid: bool,
    products: list[tuple[uuid.UUID, str, str]],
    has_membership: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard with one-tap product buttons + special actions.

    ``products`` — list of (product_id, label, currency-price). For brevity we
    pass at most 6 fast products; full catalogue search is V2.
    """
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for pid, label, _ in products[:6]:
        pair.append(
            InlineKeyboardButton(text=f"➕ {label}", callback_data=f"add:{pid}")
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    if has_free:
        rows.append(
            [InlineKeyboardButton(
                text="🎁 Использовать бесплатный кофе",
                callback_data="free",
            )]
        )
    if has_prepaid:
        rows.append(
            [InlineKeyboardButton(
                text="📦 Списать из пакета",
                callback_data="prepaid",
            )]
        )
    if has_membership:
        rows.append(
            [InlineKeyboardButton(
                text="🚫 Отменить абонемент",
                callback_data="vip_cancel",
            )]
        )

    rows.append(
        [
            InlineKeyboardButton(text="🪪 Принять код", callback_data="code"),
            InlineKeyboardButton(text="✅ Готово", callback_data="done"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prepaid_picker_kb(
    packages: list[tuple[uuid.UUID, str, int]],
) -> InlineKeyboardMarkup:
    """Pick which prepaid package to debit. ``packages`` = (id, label, remaining)."""
    rows = [
        [InlineKeyboardButton(
            text=f"📦 {label} · ост. {remaining}",
            callback_data=f"prep_pkg:{pkg_id}",
        )]
        for pkg_id, label, remaining in packages
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="prep_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def free_picker_kb(
    cards: list[tuple[uuid.UUID, str]],
) -> InlineKeyboardMarkup:
    """Pick which loyalty card's free coffee to redeem. ``cards`` = (id, label)."""
    rows = [
        [InlineKeyboardButton(
            text=f"🎁 {label}",
            callback_data=f"free_card:{card_id}",
        )]
        for card_id, label in cards
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="free_no")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(
    *,
    yes_data: str,
    no_data: str = "cancel",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=yes_data),
                InlineKeyboardButton(text="✖️ Нет", callback_data=no_data),
            ]
        ]
    )
