"""Живой поиск в интернете для информационного режима (ADR-0006)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ai_trainer.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    content: str = ""


@runtime_checkable
class SearchProvider(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]: ...


class DuckDuckGoProvider:
    """Поиск через ddgs (без API-ключей)."""

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        import anyio

        def _run() -> list[SearchResult]:
            import time

            from ddgs import DDGS

            # yahoo/startpage таймаутятся из РФ и растягивают ожидание;
            # ddgs опрашивает движки параллельно и ранжирует результаты.
            backend = "duckduckgo,google,brave,mojeek,wikipedia"
            # Антибот-анomaly DuckDuckGo кратковременно банит IP (окно ~15 с)
            # при частых запросах — повторяем с растущей паузой.
            delays = (5, 15)
            last_exc: Exception | None = None
            for attempt in range(len(delays) + 1):
                try:
                    with DDGS(timeout=5) as ddgs:
                        items = ddgs.text(query, max_results=limit, backend=backend)
                    return [
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("href", ""),
                            snippet=item.get("body", ""),
                        )
                        for item in items
                    ]
                except Exception as exc:
                    last_exc = exc
                    if attempt < len(delays):
                        time.sleep(delays[attempt])
            raise RuntimeError("web search failed") from last_exc

        return await anyio.to_thread.run_sync(_run)


class CachedSearchProvider:
    """TTL-кэш успешных выдач: защита от повторов и антибот-бана DDG."""

    def __init__(self, provider: SearchProvider, *, ttl_seconds: float) -> None:
        self._provider = provider
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, list[SearchResult]]] = {}

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        key = " ".join(query.lower().split())
        cached = self._cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < self._ttl:
            return list(cached[1])
        results = await self._provider.search(query, limit=limit)
        if results:
            self._cache[key] = (time.monotonic(), list(results))
        return results


def build_search_provider() -> SearchProvider | None:
    """Провайдер поиска или None, если он недоступен."""

    try:
        import ddgs  # noqa: F401
    except Exception:
        return None
    return CachedSearchProvider(
        DuckDuckGoProvider(), ttl_seconds=get_settings().web_search_cache_ttl
    )
