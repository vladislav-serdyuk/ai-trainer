"""Обработка inline-кнопок."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from ai_trainer.bot.deps import get_orchestrator
from ai_trainer.bot.handlers.utils import send_reply
from ai_trainer.pipeline.context import Reply
from ai_trainer.pipeline.states import (
    PREFIX_CONSENT,
    PREFIX_MENU,
    PREFIX_MODE,
    PREFIX_SCENARIO,
    parse_callback,
)

router = Router(name="callbacks")


@router.callback_query()
async def handle_callback(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass

    if callback.from_user is None or not isinstance(callback.message, Message):
        return

    user_id = callback.from_user.id
    orchestrator = get_orchestrator()
    prefix, value = parse_callback(callback.data or "")

    if prefix == PREFIX_CONSENT:
        reply = await orchestrator.handle_consent(user_id)
    elif prefix == PREFIX_SCENARIO:
        reply = await orchestrator.handle_scenario(user_id, value)
    elif prefix == PREFIX_MODE:
        reply = await orchestrator.handle_mode(user_id, value)
    elif prefix == PREFIX_MENU:
        reply = await orchestrator.handle_menu(user_id)
    else:
        reply = Reply(text="Не понял кнопку. Открой меню: /menu")

    await send_reply(callback.message, reply)
