"""Репозиторий кейсов тренажёра."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.models import Case


class CaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_scenario(self, scenario_code: str) -> list[Case]:
        result = await self._session.execute(
            select(Case)
            .where(Case.scenario_code == scenario_code)
            .order_by(Case.sort_order, Case.id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, case_id: int) -> Case | None:
        return await self._session.get(Case, case_id)
