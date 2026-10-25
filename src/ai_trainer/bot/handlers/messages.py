"""Обработка текстовых и голосовых сообщений."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import Message

from ai_trainer.bot.deps import get_orchestrator
from ai_trainer.bot.handlers.utils import send_reply

router = Router(name="messages")


@router.message(F.voice | F.audio)
async def handle_voice(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    media = message.voice or message.audio
    if media is None:
        return
    buffer = await bot.download(media)
    if buffer is None:
        return
    reply = await get_orchestrator().handle_voice(message.from_user.id, buffer.read())
    await send_reply(message, reply)


@router.message(F.text)
async def handle_text(message: Message) -> None:
    if message.from_user is None or not message.text:
        return
    reply = await get_orchestrator().handle_text(message.from_user.id, message.text)
    await send_reply(message, reply)
