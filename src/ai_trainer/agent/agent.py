# Copyright (C) 2026 AI Trainer contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Агент: собирает промпт, контекст KB, инструменты и получает ответ LLM."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_trainer.agent.client import LLMClient, Message
from ai_trainer.agent.schemas import Citation, InfoAnswer, TrainerEvaluation
from ai_trainer.agent.tools.base import ToolSpec
from ai_trainer.agent.tools.retriever import build_retriever_tool
from ai_trainer.agent.tools.web_cleanup import (
    format_web_results,
    normalize_url,
    select_web_results,
)
from ai_trainer.agent.tools.web_page import WebPageLoader
from ai_trainer.agent.tools.web_search import SearchProvider, SearchResult
from ai_trainer.config import Settings, get_settings
from ai_trainer.prompts import load_prompt
from ai_trainer.rag.citations import citation_from_document, deduplicate
from ai_trainer.rag.embeddings import Embedder
from ai_trainer.rag.rerank import Reranker, get_reranker
from ai_trainer.rag.retrieve import Retriever
from ai_trainer.repository.enums import Verdict
from ai_trainer.repository.models import Case, CaseAnswer, Mistake
from ai_trainer.repository.repos.catalog import MistakeRepository
from ai_trainer.repository.repos.knowledge import KnowledgeRepository, RetrievedChunk

logger = logging.getLogger(__name__)


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    if not chunks:
        return "(пусто — по этому запросу нет материалов в базе знаний)"
    blocks = []
    for i, chunk in enumerate(chunks, 1):
        blocks.append(
            f"[{i}] {chunk.title} ({chunk.source_type.value}), "
            f"document_id={chunk.document_id}\n{chunk.url}\n{chunk.content}"
        )
    return "\n\n".join(blocks)


def _messages_with_system(system: str, history: Sequence[Message], user: str) -> list[Message]:
    messages: list[Message] = [{"role": "system", "content": system}]
    messages.extend(dict(item) for item in history)
    messages.append({"role": "user", "content": user})
    return messages


class Agent:
    def __init__(
        self,
        session: AsyncSession,
        *,
        llm: LLMClient | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        search_provider: SearchProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session = session
        self._llm = llm or LLMClient(self._settings)
        self._reranker = reranker or get_reranker()
        self._retriever = Retriever(
            session,
            embedder=embedder,
            reranker=self._reranker,
            top_k=self._settings.retrieval_top_k,
        )
        self._search_provider = search_provider
        self._page_loader = WebPageLoader(
            timeout=self._settings.web_page_timeout,
            max_chars=self._settings.web_page_max_chars,
            ttl_seconds=self._settings.web_search_cache_ttl,
        )
        self._mistakes = MistakeRepository(session)
        self._knowledge = KnowledgeRepository(session)

    # -- tools -------------------------------------------------------------

    def _tools(self, scenario_code: str | None) -> tuple[list[ToolSpec], dict[str, Any]]:
        tool = build_retriever_tool(self._retriever, scenario_code=scenario_code)
        return [tool], {tool.name: tool.handler}

    # -- info mode ---------------------------------------------------------

    async def answer_info(
        self,
        query: str,
        *,
        scenario_title: str | None = None,
        scenario_code: str | None = None,
        history: Sequence[Message] = (),
    ) -> InfoAnswer:
        # Поиск в интернете детерминирован: код сам ищет по вопросу пользователя
        # и кладёт очищенную/отсортированную выдачу в контекст, модель решает
        # только, как её использовать. Оба источника идут параллельно.
        chunks, web_results = await asyncio.gather(
            self._retriever.search(query, scenario_code=scenario_code),
            self._web_search(query),
        )

        system = "\n\n".join(
            [
                load_prompt("persona"),
                load_prompt("info_answer"),
                f"Сценарий пользователя: {scenario_title or 'не выбран'}",
                f"Контекст из базы знаний:\n{format_context(chunks)}",
                "Результаты веб-поиска по запросу пользователя:\n"
                f"{format_web_results(web_results)}",
            ]
        )
        answer: InfoAnswer = await self._llm.chat_json(
            _messages_with_system(system, history, query), InfoAnswer
        )
        answer.citations = self._clean_citations(answer.citations, chunks, web_results)
        if not answer.citations and chunks:
            # Маленькие модели при structured output часто возвращают пустой
            # citations, хотя фактически опираются на контекст KB. Чанки выше
            # по релевантности — честное приложение того, на чём основан ответ.
            fallback = [
                Citation(
                    document_id=c.document_id,
                    url=c.url,
                    title=c.title,
                    source_type=c.source_type.value,
                    quote=c.content[:200],
                ).model_dump()
                for c in chunks[:3]
            ]
            answer.citations = [Citation.model_validate(x) for x in deduplicate(fallback)]
        return answer

    async def _web_search(self, query: str) -> list[SearchResult]:
        """Веб-выдача по вопросу: fetch → чистка → реранк → top-N."""

        if not self._settings.web_search_enabled or self._search_provider is None:
            return []
        started = time.monotonic()
        try:
            fetched = await self._search_provider.search(query, limit=self._settings.web_fetch_limit)
        except Exception as exc:
            # Поиск — дополнение к KB; его недоступность не должна ломать диалог.
            logger.warning("web_search %r failed: %s", query, exc)
            return []
        selected = select_web_results(
            query,
            fetched,
            self._reranker,
            top_k=self._settings.web_results_in_context,
            per_domain=self._settings.web_results_per_domain,
        )
        selected = await self._load_pages(selected)
        logger.info(
            "web_search %r: fetched %d, selected %d, pages %d, %.1fs",
            query,
            len(fetched),
            len(selected),
            sum(1 for item in selected if item.content),
            time.monotonic() - started,
        )
        return selected

    async def _load_pages(self, results: Sequence[SearchResult]) -> list[SearchResult]:
        """Дополнить top-N результатов текстом страницы (снипет бывает пустым)."""

        if not self._settings.web_search_page_fetch or not results:
            return list(results)
        targets = results[: self._settings.web_search_page_count]
        texts = await asyncio.gather(*(self._page_loader.load(item.url) for item in targets))
        content_by_url = {item.url: text for item, text in zip(targets, texts, strict=True) if text}
        if not content_by_url:
            return list(results)
        return [
            SearchResult(
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                content=content_by_url.get(item.url, item.content),
            )
            for item in results
        ]

    @staticmethod
    def _clean_citations(
        citations: list[Citation],
        chunks: Sequence[RetrievedChunk],
        web_results: Sequence[SearchResult],
    ) -> list[Citation]:
        """Allowlist-цитаты: только url реально найденных чанков KB и веб-выдачи.

        Метаданные источника авторитетнее вывода модели: KB-цитату сверяем по
        нормализованному url с чанком, веб-цитату — с результатом поиска.
        Всё, чего нет в allowlist (выдуманные ссылки), отбрасывается.
        """

        chunk_by_url = {normalize_url(c.url): c for c in chunks}
        web_by_url = {normalize_url(r.url): r for r in web_results}
        items: list[dict[str, Any]] = []
        for c in citations:
            if not c.url:
                continue
            key = normalize_url(c.url)
            chunk = chunk_by_url.get(key)
            if chunk is not None:
                items.append(
                    c.model_copy(
                        update={
                            "url": chunk.url,
                            "document_id": chunk.document_id,
                            "title": chunk.title,
                            "source_type": chunk.source_type.value,
                        }
                    ).model_dump()
                )
                continue
            web = web_by_url.get(key)
            if web is not None:
                items.append(
                    c.model_copy(
                        update={
                            "url": web.url,
                            "document_id": None,
                            "title": web.title or web.url,
                            "source_type": "media",
                            "quote": c.quote or web.snippet[:200],
                        }
                    ).model_dump()
                )
                continue
            logger.info("citation dropped (not in allowlist): %s", c.url)
        return [Citation.model_validate(item) for item in deduplicate(items)]

    # -- trainer mode ------------------------------------------------------

    async def evaluate_answer(
        self,
        case: Case,
        answer_text: str,
        *,
        scenario_title: str | None = None,
        scenario_code: str | None = None,
        history: Sequence[Message] = (),
    ) -> TrainerEvaluation:
        mistakes = await self._mistakes.get_codes(case.mistake_codes)
        documents = await self._knowledge.get_documents(case.document_ids)
        retrieval = await self._retriever.search(case.prompt, scenario_code=scenario_code, top_k=3)

        system_parts = [
            load_prompt("persona"),
            load_prompt("evaluate"),
            f"Сценарий: {scenario_title or '—'}",
            f"Кейс: {case.title}\nВопрос: {case.prompt}",
            "Эталонные пункты ответа:\n- " + "\n- ".join(case.expected_points or ["нет"]),
            f"Удачный пример ответа:\n{case.exemplary_answer}",
            self._mistakes_block(mistakes),
            f"Контекст из базы знаний:\n{format_context(retrieval)}",
            "Источники, на которые ссылается кейс:\n"
            + "\n".join(f"- {d.title}: {d.url}" for d in documents),
        ]
        tools, dispatch = self._tools(scenario_code)

        evaluation = await self._llm.chat_json(
            _messages_with_system("\n\n".join(system_parts), history, answer_text),
            TrainerEvaluation,
            tools=tools,
            tool_dispatch=dispatch,
        )
        return self._sanitize_evaluation(evaluation, case, documents, retrieval)

    @staticmethod
    def _mistakes_block(mistakes: Sequence[Mistake]) -> str:
        if not mistakes:
            return "Типовые ошибки этого кейса: (нет перечисленных)"
        lines = []
        for mistake in mistakes:
            line = f"- {mistake.code}: {mistake.description}"
            if mistake.improved_wording:
                line += f"\n  Улучшенная формулировка: {mistake.improved_wording}"
            lines.append(line)
        return "Типовые ошибки этого кейса:\n" + "\n".join(lines)

    @staticmethod
    def _sanitize_evaluation(
        evaluation: TrainerEvaluation,
        case: Case,
        documents: Sequence[Any],
        retrieval: Sequence[RetrievedChunk],
    ) -> TrainerEvaluation:
        # Ограничить коды ошибок списком кейса, чтобы модель не выдумывала.
        allowed = set(case.mistake_codes)
        evaluation.detected_mistakes = [
            code for code in evaluation.detected_mistakes if code in allowed
        ]
        if evaluation.verdict not in set(Verdict):
            evaluation.verdict = Verdict.partial

        base = [citation_from_document(d) for d in documents]
        from_rag = [
            Citation(
                document_id=c.document_id,
                url=c.url,
                title=c.title,
                source_type=c.source_type.value,
                quote=c.content[:200],
            )
            for c in retrieval
        ]
        merged = deduplicate(
            base
            + [c.model_dump() for c in from_rag]
            + [c.model_dump() for c in evaluation.citations]
        )
        evaluation.citations = [Citation.model_validate(item) for item in merged]
        return evaluation

    # -- summary -----------------------------------------------------------

    async def summarize(
        self,
        answers: Sequence[CaseAnswer],
        *,
        scenario_title: str | None = None,
        history: Sequence[Message] = (),
    ) -> str:
        lines = []
        for answer in answers:
            line = f"- вердикт: {answer.verdict.value}"
            if answer.what_to_improve:
                line += f"; улучшить: {answer.what_to_improve[:120]}"
            if answer.detected_mistakes:
                line += f"; ошибки: {', '.join(answer.detected_mistakes)}"
            lines.append(line)

        system = "\n\n".join(
            [load_prompt("persona"), load_prompt("summary"), f"Сценарий: {scenario_title or '—'}"]
        )
        user = "Результаты разбора ответов:\n" + ("\n".join(lines) or "(нет ответов)")
        return await self._llm.chat_text(_messages_with_system(system, history, user))
