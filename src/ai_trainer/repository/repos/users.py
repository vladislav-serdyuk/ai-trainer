"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.models import CaseAnswer, Message, User
from ai_trainer.repository.models import Session as Dialog


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_or_create(self, telegram_id: int) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id)
            self._session.add(user)
            await self._session.flush()
        return user

    async def set_consent(self, user: User) -> User:
        user.consent_at = datetime.now(UTC)
        await self._session.flush()
        return user

    async def soft_delete(self, user: User) -> None:
        user.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def purge(self, user: User) -> None:
        """Удалить историю пользователя по команде /delete."""

        session_ids = select(Dialog.id).where(Dialog.user_id == user.id)
        await self._session.execute(
            delete(CaseAnswer).where(CaseAnswer.session_id.in_(session_ids))
        )
        await self._session.execute(delete(Message).where(Message.session_id.in_(session_ids)))
        await self._session.execute(delete(Dialog).where(Dialog.user_id == user.id))
        user.consent_at = None
        user.deleted_at = datetime.now(UTC)
        await self._session.flush()
