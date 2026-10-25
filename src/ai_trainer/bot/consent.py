"""Согласие пользователя: экран с документами и middleware-гейт.

Согласие — забота слоя бота (презентация документов, кнопка, перехват
апдейтов), а не пайплайна: Orchestrator не знает о gate. См. architecture.md §4.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, FSInputFile, Message, TelegramObject

from ai_trainer.bot.keyboards.menu import consent_markup
from ai_trainer.config import get_settings
from ai_trainer.pipeline import format as fmt
from ai_trainer.pipeline.states import CONSENT_CB
from ai_trainer.repository.repos.users import UserRepository
from ai_trainer.repository.session import session_scope

logger = logging.getLogger(__name__)

def get_consent_text() -> str:
    settings = get_settings()
    code_link = f" [Исходный код]({settings.source_code_url})" if settings.source_code_url else ""
    return (
        "Прежде чем начать: я буду хранить только id Telegram и содержание диалога "
        "в рамках сессии. Рекомендации носят информационный характер и не заменяют "
        "официальные требования вузов и работодателей.\n\n"
        f"Программа распространяется под лицензией GNU AGPLv3.{code_link}\n\n"
        "Ниже — документы. Продолжая, ты соглашаешься с политикой конфиденциальности и EULA."
    )

_LEGAL_DIR = Path(__file__).resolve().parents[3] / "legal_texts"
_LEGAL_DOCS = (
    ("pp.md", "Политика конфиденциальности"),
    ("eula.md", "Пользовательское соглашение (EULA)"),
)


async def user_has_consent(user_id: int) -> bool:
    """Проверить `users.consent_at` (bot → repository допустимо, ADR-0009)."""

    async with session_scope() as session:
        user = await UserRepository(session).get_by_telegram_id(user_id)
        return user is not None and user.consent_at is not None


async def send_consent_screen(message: Message) -> None:
    """Аннотация бота + текст согласия + pp.md + eula.md + кнопка «Согласен»."""

    await message.answer(f"{fmt.about_text()}\n\n{get_consent_text()}", reply_markup=consent_markup())
    for filename, caption in _LEGAL_DOCS:
        path = _LEGAL_DIR / filename
        if not path.exists():
            logger.warning("legal document not found: %s", path)
            continue
        await message.answer_document(FSInputFile(path), caption=caption)


class ConsentMiddleware(BaseMiddleware):
    """Гейт: без согласия пускаем только колбэк «Согласен»."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or await user_has_consent(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == CONSENT_CB:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer()
            if isinstance(event.message, Message):
                await send_consent_screen(event.message)
            return None
        if isinstance(event, Message):
            await send_consent_screen(event)
            return None
        return await handler(event, data)
