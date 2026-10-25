"""Сборка ссылок на источники (цитирование обязательно по заданию)."""

from __future__ import annotations

from typing import Any

from ai_trainer.repository.models import Document
from ai_trainer.repository.repos.knowledge import RetrievedChunk


def _quote(content: str, limit: int = 200) -> str:
    text = " ".join(content.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def citation_from_chunk(chunk: RetrievedChunk) -> dict[str, Any]:
    """Цитата, полученная в ходе ретрива (источник + фрагмент текста)."""

    return {
        "document_id": chunk.document_id,
        "url": chunk.url,
        "title": chunk.title,
        "source_type": chunk.source_type.value,
        "quote": _quote(chunk.content),
    }


def citation_from_document(document: Document) -> dict[str, Any]:
    """Ссылка на документ KB без конкретного фрагмента (кейсы, ошибки)."""

    return {
        "document_id": document.id,
        "url": document.url,
        "title": document.title,
        "source_type": document.source_type.value,
        "quote": None,
    }


def deduplicate(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Убрать дубли по url (или document_id, если url нет), сохранив порядок."""

    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for citation in citations:
        # url стабильно идентифицирует источник (KB и веб); document_id — запасной
        # ключ. Один ключ-тип, чтобы один и тот же источник не задвоился.
        key: Any = citation.get("url") or citation.get("document_id")
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique
