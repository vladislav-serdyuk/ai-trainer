from __future__ import annotations

from collections.abc import Sequence

from ai_trainer.agent.tools.web_cleanup import format_web_results
from ai_trainer.agent.tools.web_search import (
    CachedSearchProvider,
    SearchResult,
)


class FakeProvider:
    def __init__(self, results: Sequence[SearchResult]) -> None:
        self._results = list(results)
        self.calls = 0

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        self.calls += 1
        return list(self._results)


def _result() -> SearchResult:
    return SearchResult("title", "https://a.ru/page", "snippet")


async def test_cache_hit_ignores_case_and_spaces() -> None:
    provider = FakeProvider([_result()])
    cached = CachedSearchProvider(provider, ttl_seconds=600)

    await cached.search("Что такое  GPA?")
    await cached.search("  что такое gpa? ")

    assert provider.calls == 1


async def test_empty_results_are_not_cached() -> None:
    provider = FakeProvider([])
    cached = CachedSearchProvider(provider, ttl_seconds=600)

    await cached.search("q")
    await cached.search("q")

    assert provider.calls == 2


async def test_zero_ttl_disables_cache() -> None:
    provider = FakeProvider([_result()])
    cached = CachedSearchProvider(provider, ttl_seconds=0)

    await cached.search("q")
    await cached.search("q")

    assert provider.calls == 2


def test_format_web_results_marks_empty_and_numbers_items() -> None:
    assert format_web_results([]) == "(веб-поиск не дал результатов)"

    block = format_web_results([_result()])
    assert block.startswith("[W1] title")
    assert "https://a.ru/page" in block
    assert "snippet" in block
