"""Загрузка и вставка источников KB в БД (этап 1).

Формат источника — JSON-файл в `knowledge_base/sources/`:

    {
      "title": "...",
      "url": "...",
      "source_type": "official",
      "scenario_code": "job_search",
      "author": "...",
      "license": "...",
      "accessed_at": "2026-10-16",
      "text": "..."
    }
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.rag.chunking import approximate_token_count, chunk_text
from ai_trainer.rag.embeddings import Embedder, get_embedder
from ai_trainer.repository.enums import SourceType
from ai_trainer.repository.models import Chunk
from ai_trainer.repository.repos.knowledge import KnowledgeRepository
from ai_trainer.repository.session import session_scope

DEFAULT_SOURCES_DIR = Path("knowledge_base/sources")


class SourceDocument(BaseModel):
    title: str
    url: str
    source_type: SourceType
    scenario_code: str | None = None
    author: str | None = None
    license: str | None = None
    accessed_at: date
    text: str


def load_sources(directory: Path) -> list[SourceDocument]:
    sources: list[SourceDocument] = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        sources.append(SourceDocument.model_validate(raw))
    return sources


async def _document_has_chunks(session: AsyncSession, document_id: int) -> bool:
    count = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    )
    return bool(count)


async def ingest_sources(
    session: AsyncSession,
    sources: list[SourceDocument],
    embedder: Embedder | None = None,
    *,
    chunk_chars: int = 900,
) -> tuple[int, int]:
    """Вставить/обновить документы и чанки. Вернуть (документов, чанков)."""

    embedder = embedder or get_embedder()
    repo = KnowledgeRepository(session)
    docs_count = 0
    chunks_count = 0

    for source in sources:
        document = await repo.upsert_document(
            title=source.title,
            url=source.url,
            source_type=source.source_type,
            accessed_at=source.accessed_at,
            scenario_code=source.scenario_code,
            author=source.author,
            license=source.license,
        )
        if await _document_has_chunks(session, document.id):
            continue

        texts = chunk_text(source.text, max_chars=chunk_chars)
        if not texts:
            continue

        embeddings = embedder.embed_documents(texts)
        for index, (content, embedding) in enumerate(zip(texts, embeddings, strict=True)):
            await repo.add_chunk(
                document_id=document.id,
                chunk_index=index,
                content=content,
                embedding=embedding,
                token_count=approximate_token_count(content),
            )
            chunks_count += 1
        docs_count += 1

    return docs_count, chunks_count


async def run_ingest(directory: Path = DEFAULT_SOURCES_DIR) -> tuple[int, int]:
    sources = load_sources(directory)
    async with session_scope() as session:
        result = await ingest_sources(session, sources)
    return result


def main() -> None:
    docs, chunks = asyncio.run(run_ingest())
    print(f"ingested documents={docs} chunks={chunks}")


if __name__ == "__main__":
    main()
