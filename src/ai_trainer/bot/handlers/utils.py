"""Общие помощники хендлеров."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from ai_trainer.bot.keyboards.menu import build_markup
from ai_trainer.pipeline.context import Reply

logger = logging.getLogger(__name__)


async def send_reply(message: Message, reply: Reply) -> None:
    try:
        await message.answer(
            reply.text,
            reply_markup=build_markup(reply),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        logger.warning("Markdown parse failed (%s), falling back to plain text", exc)
        await message.answer(
            reply.text,
            reply_markup=build_markup(reply),
            disable_web_page_preview=True,
            parse_mode=None,
        )
