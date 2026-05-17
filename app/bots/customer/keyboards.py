"""Reply and inline keyboards for the customer bot."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bots.customer import texts


def share_contact_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.t("share_btn", lang), request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.t("btn.redeem", lang))],
            [KeyboardButton(text=texts.t("btn.history", lang)),
             KeyboardButton(text=texts.t("btn.refresh", lang))],
            [KeyboardButton(text=texts.t("btn.lang", lang))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def lang_picker_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.t("lang.btn.ru", "ru"), callback_data="lang:ru")],
        [InlineKeyboardButton(text=texts.t("lang.btn.uz", "uz"), callback_data="lang:uz")],
    ])


def empty_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[])
