"""Репозитории справочников: сценарии и каталог ошибок."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.models import Mistake, Scenario


class ScenarioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Scenario]:
        result = await self._session.execute(
            select(Scenario).order_by(Scenario.sort_order, Scenario.code)
        )
        return list(result.scalars().all())

    async def get(self, code: str) -> Scenario | None:
        return await self._session.get(Scenario, code)


class MistakeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_scenario(self, scenario_code: str | None) -> list[Mistake]:
        stmt = select(Mistake)
        if scenario_code is not None:
            stmt = stmt.where(
                (Mistake.scenario_code == scenario_code) | (Mistake.scenario_code.is_(None))
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_codes(self, codes: list[str]) -> list[Mistake]:
        if not codes:
            return []
        result = await self._session.execute(select(Mistake).where(Mistake.code.in_(codes)))
        return list(result.scalars().all())
