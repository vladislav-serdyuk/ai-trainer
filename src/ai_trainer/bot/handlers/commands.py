"""Команды бота."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ai_trainer.bot.deps import get_orchestrator
from ai_trainer.bot.handlers.utils import send_reply

router = Router(name="commands")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user is None:
        return
    reply = await get_orchestrator().handle_start(message.from_user.id)
    await send_reply(message, reply)


@router.message(Command("menu"))
async def handle_menu(message: Message) -> None:
    if message.from_user is None:
        return
    reply = await get_orchestrator().handle_menu(message.from_user.id)
    await send_reply(message, reply)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    if message.from_user is None:
        return
    reply = await get_orchestrator().handle_help(message.from_user.id)
    await send_reply(message, reply)


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    if message.from_user is None:
        return
    reply = await get_orchestrator().handle_stop(message.from_user.id)
    await send_reply(message, reply)


@router.message(Command("delete"))
async def handle_delete(message: Message) -> None:
    if message.from_user is None:
        return
    reply = await get_orchestrator().handle_delete(message.from_user.id)
    await send_reply(message, reply)
