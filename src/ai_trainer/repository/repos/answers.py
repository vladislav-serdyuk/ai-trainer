"""Репозиторий результатов разбора ответов (Этап 3)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.enums import Verdict
from ai_trainer.repository.models import CaseAnswer


class CaseAnswerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        session_id: int,
        case_id: int,
        user_answer: str,
        verdict: Verdict,
        score: int | None = None,
        what_to_improve: str | None = None,
        example_answer: str | None = None,
        detected_mistakes: list[str] | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> CaseAnswer:
        answer = CaseAnswer(
            session_id=session_id,
            case_id=case_id,
            user_answer=user_answer,
            verdict=verdict,
            score=score,
            what_to_improve=what_to_improve,
            example_answer=example_answer,
            detected_mistakes=detected_mistakes or [],
            citations=citations,
        )
        self._session.add(answer)
        await self._session.flush()
        return answer

    async def list_by_session(self, session_id: int) -> list[CaseAnswer]:
        result = await self._session.execute(
            select(CaseAnswer)
            .where(CaseAnswer.session_id == session_id)
            .order_by(CaseAnswer.created_at, CaseAnswer.id)
        )
        return list(result.scalars().all())
