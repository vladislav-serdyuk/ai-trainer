#!/usr/bin/env python3
"""CLI-тестер бота: диалог из консоли через настоящий dispatcher без Telegram.

Запуск (из корня репозитория):

    uv run python tools/bot_cli.py [--user 42]

Как работает:
- MockSession подменяет aiohttp-сессию aiogram: перехватывает SendMessage /
  AnswerCallbackQuery и печатает их в терминал.
- Каждая строка ввода превращается в Update и прогоняется через
  build_dispatcher() → хендлеры → Orchestrator → PostgreSQL.
- Ответы бота печатаются с нумерованными кнопками; ввод номера = нажатие кнопки.
- Реальный LLM (Ollama) и реальная БД (localhost:5433) — как в проде.

Служебные команды: :help, :state, :quit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import AnswerCallbackQuery, GetMe, SendDocument, SendMessage
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
)

from ai_trainer.bot.main import build_dispatcher
from ai_trainer.repository.repos.sessions import SessionRepository
from ai_trainer.repository.repos.users import UserRepository
from ai_trainer.repository.session import dispose_engine, session_scope

HELP = """\
Команды CLI:
  <текст>       обычное сообщение боту
  /start /menu /help /stop /delete   команды бота
  1..N         нажать кнопку №N из последней клавиатуры
  :state       показать состояние сессии в БД
  :help        эта справка
  :quit        выход
"""

_CLI_TOKEN = "42:cli-test-token"  # формат валиден; в Telegram не ходим


class MockSession(BaseSession):
    """Сессия, которая ничего не отправляет в Telegram, а записывает вызовы."""

    def __init__(self) -> None:
        super().__init__()
        self.outbox: list[SendMessage | SendDocument] = []
        self.last_message: Message | None = None

    async def make_request(
        self,
        bot: Bot,
        method: object,
        timeout: int | None = None,  # noqa: ASYNC109 — сигнатура BaseSession
    ) -> object:
        if isinstance(method, SendMessage):
            self.outbox.append(method)
            self.last_message = Message(
                message_id=len(self.outbox),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                from_user=User(id=42, is_bot=True, first_name="Bot"),
                text=method.text,
            )
            return self.last_message
        if isinstance(method, SendDocument):
            self.outbox.append(method)
            self.last_message = Message(
                message_id=len(self.outbox),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                from_user=User(id=42, is_bot=True, first_name="Bot"),
                text=method.caption or "",
            )
            return self.last_message
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="CLI", username="cli_bot")
        return True

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: object, **kwargs: object):
        raise NotImplementedError("Скачивание файлов не поддерживается в CLI")


class Cli:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self.session = MockSession()
        self.bot = Bot(
            token=_CLI_TOKEN,
            session=self.session,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
        self.dispatcher = build_dispatcher()
        self.last_buttons: list[str] = []  # callback_data по номерам
        self._update_id = 0

    def _next_id(self) -> int:
        self._update_id += 1
        return self._update_id

    async def send_text(self, text: str) -> None:
        update = Update(
            update_id=self._next_id(),
            message=Message(
                message_id=self._next_id(),
                date=datetime.now(UTC),
                chat=Chat(id=self.user_id, type="private"),
                from_user=User(id=self.user_id, is_bot=False, first_name="Tester"),
                text=text,
            ),
        )
        await self._feed(update)

    async def press(self, data: str) -> None:
        assert self.session.last_message is not None, "нет сообщения бота для кнопки"
        update = Update(
            update_id=self._next_id(),
            callback_query=CallbackQuery(
                id=str(self._next_id()),
                from_user=User(id=self.user_id, is_bot=False, first_name="Tester"),
                chat_instance="cli",
                data=data,
                message=self.session.last_message,
            ),
        )
        await self._feed(update)

    async def _feed(self, update: Update) -> None:
        try:
            await self.dispatcher.feed_update(bot=self.bot, update=update)
        except Exception:
            logging.exception("Ошибка обработки апдейта")
        await self._drain()

    async def _drain(self) -> None:
        outbox, self.session.outbox = self.session.outbox, []
        self.last_buttons = []
        for msg in outbox:
            if isinstance(msg, SendDocument):
                doc = msg.document
                name = getattr(doc, "filename", None) or "документ"
                caption = msg.caption or ""
                print(f"\n\N{PAPERCLIP} {name}" + (f"\n{caption}" if caption else ""))
                continue
            print(f"\n\N{ROBOT FACE} bot:\n{msg.text}")
            markup = msg.reply_markup
            if isinstance(markup, InlineKeyboardMarkup):
                for row in markup.inline_keyboard:
                    for button in row:
                        self.last_buttons.append(button.callback_data or "")
                        idx = len(self.last_buttons)
                        print(f"  [{idx}] {button.text}")

    async def show_state(self) -> None:
        async with session_scope() as db:
            user = await UserRepository(db).get_by_telegram_id(self.user_id)
            if user is None:
                print("Пользователь не создан (нет в БД).")
                return
            active = await SessionRepository(db).get_active(user.id)
            print(f"user telegram_id={user.telegram_id} consent={user.consent_at}")
            if active is None:
                print("Активной сессии нет.")
                return
            print(
                f"session id={active.id} state={active.state} "
                f"scenario={active.scenario_code} mode={active.mode} "
                f"case_index={active.case_index} case_ids={active.case_ids}"
            )


async def run_repl(cli: Cli) -> None:
    print("CLI-тестер бота. :help — справка, :quit — выход.\n")
    await cli.send_text("/start")
    while True:
        try:
            line = await asyncio.to_thread(input, "\nвы> ")
        except (EOFError, KeyboardInterrupt):
            break
        line = line.strip()
        if not line:
            continue
        if line in (":quit", ":q", ":exit"):
            break
        if line in (":help", ":h"):
            print(HELP)
            continue
        if line == ":state":
            await cli.show_state()
            continue
        if line.isdigit():
            idx = int(line)
            if 1 <= idx <= len(cli.last_buttons):
                await cli.press(cli.last_buttons[idx - 1])
            else:
                print(f"Нет кнопки №{idx}. Доступно: 1..{len(cli.last_buttons)}")
            continue
        await cli.send_text(line)


async def amain(user_id: int) -> None:
    cli = Cli(user_id)
    try:
        await run_repl(cli)
    finally:
        await cli.bot.session.close()
        await dispose_engine()
    print("Пока!")


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI-тестер Telegram-бота")
    parser.add_argument(
        "--user", type=int, default=42, help="user_id для симуляции (по умолчанию 42)"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # aiogram пишет много INFO — приглушаем, ошибки оставляем
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    asyncio.run(amain(args.user))


if __name__ == "__main__":
    main()
