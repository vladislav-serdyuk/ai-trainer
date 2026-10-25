"""Репозиторий базы знаний (документы и чанки с векторным поиском)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_trainer.repository.enums import SourceType
from ai_trainer.repository.models import Chunk, Document


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    content: str
    distance: float
    title: str
    url: str
    source_type: SourceType


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_document(
        self,
        *,
        title: str,
        url: str,
        source_type: SourceType,
        accessed_at: date,
        scenario_code: str | None = None,
        author: str | None = None,
        license: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Document:
        result = await self._session.execute(select(Document).where(Document.url == url))
        document = result.scalar_one_or_none()
        if document is None:
            document = Document(
                title=title,
                url=url,
                source_type=source_type,
                accessed_at=accessed_at,
                scenario_code=scenario_code,
                author=author,
                license=license,
                meta=meta or {},
            )
            self._session.add(document)
            await self._session.flush()
        return document

    async def add_chunk(
        self,
        *,
        document_id: int,
        chunk_index: int,
        content: str,
        embedding: list[float],
        token_count: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Chunk:
        chunk = Chunk(
            document_id=document_id,
            chunk_index=chunk_index,
            content=content,
            embedding=embedding,
            token_count=token_count,
            meta=meta or {},
        )
        self._session.add(chunk)
        await self._session.flush()
        return chunk

    async def get_document(self, document_id: int) -> Document | None:
        return await self._session.get(Document, document_id)

    async def get_documents(self, document_ids: list[int]) -> list[Document]:
        if not document_ids:
            return []
        result = await self._session.execute(select(Document).where(Document.id.in_(document_ids)))
        return list(result.scalars().all())

    async def search_chunks(
        self,
        query_embedding: list[float],
        *,
        scenario_code: str | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(Chunk, Document, distance)
            .join(Document, Chunk.document_id == Document.id)
            .options(selectinload(Chunk.document))
            .order_by(distance)
            .limit(top_k)
        )
        if scenario_code is not None:
            stmt = stmt.where(
                (Document.scenario_code == scenario_code) | (Document.scenario_code.is_(None))
            )
        result = await self._session.execute(stmt)
        rows = result.all()

        chunks: list[RetrievedChunk] = []
        for chunk, document, dist in rows:
            chunks.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    content=chunk.content,
                    distance=float(dist),
                    title=document.title,
                    url=document.url,
                    source_type=document.source_type,
                )
            )
        return chunks
