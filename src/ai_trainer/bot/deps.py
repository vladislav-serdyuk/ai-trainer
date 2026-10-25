"""Единственный экземпляр оркестратора на приложение."""

from __future__ import annotations

from functools import lru_cache

from ai_trainer.agent.tools.web_search import build_search_provider
from ai_trainer.pipeline.orchestrator import Orchestrator


@lru_cache
def get_orchestrator() -> Orchestrator:
    return Orchestrator(search_provider=build_search_provider())
