"""Репозиторий сообщений."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.enums import ContentType, MessageRole
from ai_trainer.repository.models import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        session_id: int,
        *,
        role: MessageRole,
        content: str,
        content_type: ContentType = ContentType.text,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        message = Message(
            session_id=session_id,
            role=role,
            content_type=content_type,
            content=content,
            citations=citations,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_by_session(self, session_id: int) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.scalars().all())
