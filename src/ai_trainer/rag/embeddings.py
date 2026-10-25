"""Эмбеддинги: интерфейс, реализация на fastembed и заглушка для тестов.

Реальный бэкенд — fastembed (ONNX), без `torch` (ADR-0011).
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol, runtime_checkable

from ai_trainer.config import get_settings


@runtime_checkable
class Embedder(Protocol):
    """Интерфейс векторизации текстов."""

    @property
    def dim(self) -> int:
        """Размерность вектора."""
        ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Эмбеддинги для документов KB."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Эмбеддинг пользовательского запроса."""
        ...


class FastEmbedEmbedder:
    """Реализация на fastembed (ленивая инициализация модели)."""

    def __init__(self, model_name: str, dim: int) -> None:
        self._model_name = model_name
        self._dim = dim
        self._model: object | None = None

    @property
    def dim(self) -> int:
        return self._dim

    def _get_model(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        results: list[list[float]] = [
            [float(x) for x in vec]
            for vec in model.embed(texts)  # type: ignore[attr-defined]
        ]
        return results

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class FakeEmbedder:
    """Детерминированный эмбеддер для тестов (без сети и моделей)."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in text.lower().split():
            idx = abs(hash(token)) % self._dim
            vec[idx] += 1.0
        total = sum(v * v for v in vec) or 1.0
        norm = total**0.5
        return [v / norm for v in vec]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@lru_cache
def get_embedder() -> Embedder:
    """Единственный эмбеддер на приложение."""

    settings = get_settings()
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim)
