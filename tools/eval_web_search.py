#!/usr/bin/env python3
"""Сравнение вариантов веб-поиска: raw / raw+rerank / rewrite+rerank.

Сырые выдачи DDG сохраняются в снапшот и переиспользуются: все варианты
сравниваются на идентичных данных, антибот-бан не искажает замер.

Запуск:
  uv run python tools/eval_web_search.py --refresh   # обновить снапшот
  uv run python tools/eval_web_search.py             # сравнить по снапшоту
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_trainer.agent.client import LLMClient
from ai_trainer.agent.tools.web_cleanup import (
    clean_results,
    normalize_url,
    select_web_results,
)
from ai_trainer.agent.tools.web_query import rewrite_search_query
from ai_trainer.agent.tools.web_search import DuckDuckGoProvider, SearchResult
from ai_trainer.config import get_settings
from ai_trainer.rag.rerank import Reranker, get_reranker

QUESTIONS: list[dict[str, Any]] = [
    {
        "q": "какой официальный курс доллара к рублю сегодня?",
        "expect": ["cbr.ru"],
    },
    {
        "q": "какая ключевая ставка ЦБ РФ сейчас?",
        "expect": ["cbr.ru"],
    },
    {
        "q": "сроки подачи документов в вузы в 2026 году",
        "expect": ["edu.gov.ru", "gosuslugi.ru", "minobrnauki.gov.ru"],
    },
    {
        "q": "какие ЕГЭ нужны для IT-специальностей в 2026?",
        "expect": ["edu.gov.ru", "fipi.ru", "minobrnauki.gov.ru"],
    },
    {
        "q": "на что смотреть при выборе вуза?",
        "expect": [],
    },
    {
        "q": "как вести себя в первый месяц на работе?",
        "expect": [],
    },
    {
        "q": "что такое GPA?",
        "expect": [],
    },
    {
        "q": "а если я хочу в IT и бюджет ограничен, какие сроки подачи документов в 2026?",
        "expect": ["edu.gov.ru", "gosuslugi.ru", "minobrnauki.gov.ru"],
    },
]

FETCH_LIMIT = 10
MIN_RESULTS = 5
THROTTLE_SECONDS = 6.0
EMPTY_RETRY_DELAYS = (20.0, 40.0)


class CachedFetcher:
    """Снапшот сырых выдач: один запрос на уникальный query, с ретраями."""

    def __init__(
        self,
        provider: DuckDuckGoProvider,
        snapshot_path: Path,
        *,
        refresh: bool,
    ) -> None:
        self._provider = provider
        self._snapshot_path = snapshot_path
        self._refresh = refresh
        self._cache: dict[str, list[SearchResult]] = {}
        self._last_call = 0.0
        if snapshot_path.exists():
            raw: dict[str, list[dict[str, str]]] = json.loads(
                snapshot_path.read_text(encoding="utf-8")
            )
            for query, items in raw.items():
                self._cache[query] = [
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("snippet", ""),
                    )
                    for item in items
                ]
            logging.info("snapshot loaded: %s (%d queries)", snapshot_path, len(raw))
        if refresh:
            failed = [query for query, results in self._cache.items() if len(results) < MIN_RESULTS]
            for query in failed:
                del self._cache[query]
            if failed:
                logging.info("refresh: retry %d short queries", len(failed))

    async def fetch(self, query: str) -> list[SearchResult]:
        if query in self._cache:
            return self._cache[query]

        for attempt in range(len(EMPTY_RETRY_DELAYS) + 1):
            wait = THROTTLE_SECONDS - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                results = await self._provider.search(query, limit=FETCH_LIMIT)
            except Exception as exc:
                logging.warning("fetch failed for %r: %s", query, exc)
                results = []
            self._last_call = time.monotonic()
            if len(results) >= MIN_RESULTS:
                break
            if attempt < len(EMPTY_RETRY_DELAYS):
                delay = EMPTY_RETRY_DELAYS[attempt]
                logging.warning("empty results for %r, retry in %.0fs", query, delay)
                await asyncio.sleep(delay)

        self._cache[query] = results
        self._save()
        return results

    def _save(self) -> None:
        payload = {
            query: [
                {"title": item.title, "url": item.url, "snippet": item.snippet} for item in results
            ]
            for query, results in self._cache.items()
        }
        self._snapshot_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _domain(url: str) -> str:
    return urlsplit(url).netloc


def _scores(reranker: Reranker, query: str, results: Sequence[SearchResult]) -> list[float]:
    if not results:
        return []
    return reranker.rerank(query, [f"{item.title}. {item.snippet}" for item in results])


def _official_hit(results: Sequence[SearchResult], expected: Sequence[str]) -> bool | None:
    if not expected:
        return None
    domains = [_domain(item.url) for item in results]
    return any(domain.endswith(tuple(expected)) for domain in domains)


def _ser(item: SearchResult) -> dict[str, str]:
    return {"title": item.title, "url": item.url, "snippet": item.snippet}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="/tmp/opencode/web_snapshot.json")
    parser.add_argument("--json", default="/tmp/opencode/web_eval.json")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    logging.info("LLM_MODEL=%s RERANKER_MODEL=%s", settings.llm_model, settings.reranker_model)

    fetcher = CachedFetcher(DuckDuckGoProvider(), Path(args.snapshot), refresh=args.refresh)
    reranker = get_reranker()
    llm = LLMClient(settings)

    rows: list[dict[str, Any]] = []
    print(f"Модель rewrite: {settings.llm_model}\n")

    for item in QUESTIONS:
        question = str(item["q"])
        expected: list[str] = list(item["expect"])
        rewritten = await rewrite_search_query(llm, question)
        raw10 = await fetcher.fetch(question)
        rewritten10 = await fetcher.fetch(rewritten)
        fetch_ok = bool(raw10) and bool(rewritten10)

        normalized = [normalize_url(result.url) for result in raw10]
        dup_raw = len(normalized) - len(set(normalized))

        variants: list[tuple[str, list[SearchResult]]] = [
            ("raw5", list(raw10[:5])),
            ("raw10+clean", clean_results(raw10)[:5]),
            ("raw10+clean+r3", select_web_results(question, raw10, reranker, top_k=3)),
            ("raw10+clean+r5", select_web_results(question, raw10, reranker, top_k=5)),
            (
                "raw10+clean+r5 dom1",
                select_web_results(question, raw10, reranker, top_k=5, per_domain=1),
            ),
            (
                "rewrite+clean+r3",
                select_web_results(question, rewritten10, reranker, top_k=3),
            ),
            (
                "rewrite+clean+r5",
                select_web_results(question, rewritten10, reranker, top_k=5),
            ),
        ]

        print(f"Q: {question}")
        print(f"   rewrite -> {rewritten!r} (raw10={len(raw10)}, rewritten10={len(rewritten10)})")
        for name, results in variants:
            domains = Counter(_domain(result.url) for result in results)
            scores = _scores(reranker, question, results)
            top1 = round(max(scores), 2) if scores else None
            top3 = (
                round(sum(sorted(scores, reverse=True)[:3]) / min(3, len(scores)), 2)
                if scores
                else None
            )
            official = _official_hit(results, expected)
            print(
                f"   {name:<20} n={len(results)} dup_raw={dup_raw} "
                f"maxdom={max(domains.values()) if domains else 0} "
                f"top1={top1} top3={top3} official={official}"
            )
            rows.append(
                {
                    "question": question,
                    "rewritten": rewritten,
                    "variant": name,
                    "fetch_ok": fetch_ok,
                    "results": [_ser(result) for result in results],
                    "n": len(results),
                    "dup_raw": dup_raw,
                    "maxdom": max(domains.values()) if domains else 0,
                    "top1": top1,
                    "top3": top3,
                    "official": official,
                }
            )
        if not fetch_ok:
            print("   ! вопрос исключён из сводки: неполная выдача DDG")
        print()

    print("СВОДКА (только вопросы с полной выдачей)")
    print(
        f"{'variant':<20} {'mean_top1':>10} {'mean_top3':>10} "
        f"{'official':>10} {'avg_n':>7} {'avg_maxdom':>11}"
    )
    variant_names = [str(row["variant"]) for row in rows]
    order = list(dict.fromkeys(variant_names))
    for name in order:
        subset = [row for row in rows if row["variant"] == name and row["fetch_ok"]]
        scored = [row for row in subset if row["top1"] is not None]
        official_rows = [row for row in subset if row["official"] is not None]
        mean_top1 = sum(row["top1"] for row in scored) / len(scored) if scored else None
        mean_top3 = sum(row["top3"] for row in scored) / len(scored) if scored else None
        hit_rate = (
            sum(1 for row in official_rows if row["official"]) / len(official_rows)
            if official_rows
            else None
        )
        avg_n = sum(row["n"] for row in subset) / len(subset) if subset else 0.0
        avg_maxdom = sum(row["maxdom"] for row in subset) / len(subset) if subset else 0.0
        print(
            f"{name:<20} "
            f"{round(mean_top1, 2) if mean_top1 is not None else '-':>10} "
            f"{round(mean_top3, 2) if mean_top3 is not None else '-':>10} "
            f"{round(hit_rate, 2) if hit_rate is not None else '-':>10} "
            f"{avg_n:>7.1f} {avg_maxdom:>11.1f}"
        )

    if fetch_ok_count := len({row["question"] for row in rows if row["fetch_ok"]}):
        print(f"\nВопросов в сводке: {fetch_ok_count} из {len(QUESTIONS)}")

    await asyncio.to_thread(
        Path(args.json).write_text,
        json.dumps(rows, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
