# Copyright (C) 2026 AI Trainer contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Точка входа бота: aiogram polling (см. architecture.md §5.1)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from ai_trainer.bot.consent import ConsentMiddleware
from ai_trainer.bot.handlers import callbacks, commands, messages
from ai_trainer.config import get_settings
from ai_trainer.repository.session import dispose_engine

logger = logging.getLogger(__name__)

_COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="menu", description="Меню сценариев"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="stop", description="Завершить текущую сессию"),
    BotCommand(command="delete", description="Удалить мои данные"),
]


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    consent = ConsentMiddleware()
    dispatcher.message.outer_middleware(consent)
    dispatcher.callback_query.outer_middleware(consent)
    dispatcher.include_router(commands.router)
    dispatcher.include_router(callbacks.router)
    dispatcher.include_router(messages.router)
    return dispatcher


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dispatcher = build_dispatcher()
    try:
        await bot.set_my_commands(_COMMANDS)
    except Exception:
        logger.warning("Не удалось установить команды бота", exc_info=True)
    logger.info("Бот запущен")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
