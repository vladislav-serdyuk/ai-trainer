"""Загрузка сид-данных: сценарии, кейсы, каталог ошибок.

Запуск: `python -m ai_trainer.repository.seed`
Источник: `knowledge_base/seed/{scenarios,cases,mistakes}.json`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.repository.models import Case, Mistake, Scenario
from ai_trainer.repository.session import session_scope

SEED_DIR = Path("knowledge_base/seed")


class ScenarioSeed(BaseModel):
    code: str
    title: str
    description: str | None = None
    sort_order: int = 0


class CaseSeed(BaseModel):
    code: str
    scenario_code: str
    title: str
    prompt: str
    difficulty: int = 1
    expected_points: list[str] = Field(default_factory=list)
    exemplary_answer: str
    mistake_codes: list[str] = Field(default_factory=list)
    document_ids: list[int] = Field(default_factory=list)
    sort_order: int = 0


class MistakeSeed(BaseModel):
    code: str
    scenario_code: str | None = None
    description: str
    trigger_examples: list[str] = Field(default_factory=list)
    improved_wording: str | None = None
    example_answer: str | None = None
    document_ids: list[int] = Field(default_factory=list)


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


async def _get_scenario(session: AsyncSession, code: str) -> Scenario | None:
    return await session.get(Scenario, code)


async def _upsert_scenario(session: AsyncSession, seed: ScenarioSeed) -> None:
    scenario = await _get_scenario(session, seed.code)
    if scenario is None:
        scenario = Scenario(code=seed.code)
        session.add(scenario)
    scenario.title = seed.title
    scenario.description = seed.description
    scenario.sort_order = seed.sort_order
    await session.flush()


async def _upsert_case(session: AsyncSession, seed: CaseSeed) -> None:
    case = (await session.execute(select(Case).where(Case.code == seed.code))).scalar_one_or_none()
    if case is None:
        case = Case(code=seed.code)
        session.add(case)
    case.scenario_code = seed.scenario_code
    case.title = seed.title
    case.prompt = seed.prompt
    case.difficulty = seed.difficulty
    case.expected_points = seed.expected_points
    case.exemplary_answer = seed.exemplary_answer
    case.mistake_codes = seed.mistake_codes
    case.document_ids = seed.document_ids
    case.sort_order = seed.sort_order
    await session.flush()


async def _upsert_mistake(session: AsyncSession, seed: MistakeSeed) -> None:
    mistake = await session.get(Mistake, seed.code)
    if mistake is None:
        mistake = Mistake(code=seed.code)
        session.add(mistake)
    mistake.scenario_code = seed.scenario_code
    mistake.description = seed.description
    mistake.trigger_examples = seed.trigger_examples
    mistake.improved_wording = seed.improved_wording
    mistake.example_answer = seed.example_answer
    mistake.document_ids = seed.document_ids
    await session.flush()


async def run_seed(seed_dir: Path = SEED_DIR) -> tuple[int, int, int]:
    scenarios = [ScenarioSeed.model_validate(x) for x in _load(seed_dir / "scenarios.json")]
    cases = [CaseSeed.model_validate(x) for x in _load(seed_dir / "cases.json")]
    mistakes = [MistakeSeed.model_validate(x) for x in _load(seed_dir / "mistakes.json")]

    async with session_scope() as session:
        for scenario_seed in scenarios:
            await _upsert_scenario(session, scenario_seed)
        for mistake_seed in mistakes:
            await _upsert_mistake(session, mistake_seed)
        for case_seed in cases:
            await _upsert_case(session, case_seed)
    return len(scenarios), len(cases), len(mistakes)


def main() -> None:
    scenarios, cases, mistakes = asyncio.run(run_seed())
    print(f"seeded scenarios={scenarios} cases={cases} mistakes={mistakes}")


if __name__ == "__main__":
    main()
