"""Опциональный реранк результатов ретрива (ADR-0005, ADR-0011)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol, runtime_checkable

from ai_trainer.config import get_settings

logger = logging.getLogger(__name__)


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        """Вернуть релевантность каждой пассажи к запросу (больше — лучше)."""
        ...


class NoopReranker:
    """Пустой реранкер: сохраняет исходный порядок."""

    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        return [float(len(passages) - i) for i in range(len(passages))]


class FastEmbedReranker:
    """Реранкер на fastembed (ленивая инициализация)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self._model_name)
        return self._model

    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        model = self._get_model()
        scores = model.rerank(query, list(passages))  # type: ignore[attr-defined]
        return [float(s) for s in scores]


@lru_cache
def get_reranker() -> Reranker:
    """Реранкер из конфига или пустой, если не настроен."""

    model_name = get_settings().reranker_model
    if not model_name:
        logger.info("Reranker отключён (RERANKER_MODEL не задан) — NoopReranker")
        return NoopReranker()
    logger.info("Reranker: %s", model_name)
    return FastEmbedReranker(model_name)
