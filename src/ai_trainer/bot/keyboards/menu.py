"""Рендеринг транспортно-независимого Reply в клавиатуру aiogram."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ai_trainer.pipeline.context import Reply
from ai_trainer.pipeline.states import CONSENT_CB, MENU_CB


def build_markup(reply: Reply) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=button.text, callback_data=button.data) for button in row]
        for row in reply.keyboard
        if row
    ]

    has_menu = any(button.data == MENU_CB for button in reply.flat_buttons)
    if reply.show_menu_button and not has_menu:
        rows.append([InlineKeyboardButton(text="Меню", callback_data=MENU_CB)])

    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Меню", callback_data=MENU_CB)]]
    )


def consent_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Согласен", callback_data=CONSENT_CB)]]
    )
