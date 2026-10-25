from __future__ import annotations

from collections.abc import Sequence

from ai_trainer.agent.tools.web_cleanup import (
    clean_results,
    normalize_url,
    select_web_results,
)
from ai_trainer.agent.tools.web_search import SearchResult


class FakeReranker:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        return self._scores


def test_normalize_url_strips_tracking_and_fragment() -> None:
    url = "https://CBR.ru/currency_base/daily/?utm_source=x&unidbquery.posted=true#top"
    assert normalize_url(url) == "https://cbr.ru/currency_base/daily"


def test_normalize_url_keeps_meaningful_params_sorted() -> None:
    url = "https://example.org/page?b=2&date=2026-10-19&a=1"
    assert normalize_url(url) == "https://example.org/page?a=1&b=2&date=2026-10-19"


def test_clean_results_dedupes_and_limits_domain() -> None:
    results = [
        SearchResult("A", "https://a.ru/1?utm_source=x", "s"),
        SearchResult("A dup", "https://a.ru/1", "s"),
        SearchResult("B", "https://a.ru/2", "s"),
        SearchResult("C", "https://a.ru/3", "s"),
        SearchResult("D", "https://b.ru/1", "s"),
        SearchResult("", "", ""),
    ]

    cleaned = clean_results(results, per_domain=2)

    assert [item.url for item in cleaned] == [
        "https://a.ru/1?utm_source=x",
        "https://a.ru/2",
        "https://b.ru/1",
    ]


def test_select_web_results_orders_by_score_and_trims() -> None:
    results = [
        SearchResult("low", "https://a.ru/1", "s1"),
        SearchResult("high", "https://a.ru/2", "s2"),
        SearchResult("mid", "https://b.ru/1", "s3"),
    ]
    reranker = FakeReranker([0.1, 0.9, 0.5])

    selected = select_web_results("q", results, reranker, top_k=2)

    assert [item.title for item in selected] == ["high", "mid"]


def test_select_web_results_handles_empty_input() -> None:
    reranker = FakeReranker([])
    assert select_web_results("q", [], reranker, top_k=3) == []
