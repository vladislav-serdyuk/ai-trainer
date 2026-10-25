"""Ретрив релевантных чанков: эмбеддинг → pgvector → опциональный реранк."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.config import get_settings
from ai_trainer.rag.embeddings import Embedder, get_embedder
from ai_trainer.rag.rerank import Reranker, get_reranker
from ai_trainer.repository.repos.knowledge import KnowledgeRepository, RetrievedChunk


class Retriever:
    def __init__(
        self,
        session: AsyncSession,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        top_k: int | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder or get_embedder()
        self._reranker = reranker or get_reranker()
        self._top_k = top_k or get_settings().retrieval_top_k
        self._repo = KnowledgeRepository(session)

    async def search(
        self, query: str, *, scenario_code: str | None = None, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        k = top_k or self._top_k

        embedding = await asyncio.to_thread(self._embedder.embed_query, query)
        chunks = await self._repo.search_chunks(embedding, scenario_code=scenario_code, top_k=k * 2)
        if not chunks:
            return []

        passages = [chunk.content for chunk in chunks]
        scores = await asyncio.to_thread(self._reranker.rerank, query, passages)

        ranked = sorted(zip(chunks, scores, strict=True), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _score in ranked[:k]]
