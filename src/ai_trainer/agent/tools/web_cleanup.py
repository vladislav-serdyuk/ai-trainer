"""Детерминированная очистка и отбор результатов веб-поиска."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_trainer.agent.tools.web_search import SearchResult
from ai_trainer.rag.rerank import Reranker

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {
    "fbclid",
    "from",
    "gclid",
    "ref",
    "referer",
    "referrer",
    "source",
    "spm",
    "srsltid",
    "unidbquery",
    "unidbquery.posted",
    "yclid",
}


def normalize_url(url: str) -> str:
    """Убрать фрагмент и трекинг-параметры, привести хост к нижнему регистру."""

    parts = urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PREFIXES) and key.lower() not in _TRACKING_KEYS
    )
    return urlunsplit(
        (
            parts.scheme.lower() or "https",
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            "",
        )
    )


def clean_results(results: Sequence[SearchResult], *, per_domain: int = 2) -> list[SearchResult]:
    """Дедуп по нормализованному url, отброс пустых, лимит на домен."""

    seen_urls: set[str] = set()
    domain_counts: dict[str, int] = {}
    cleaned: list[SearchResult] = []
    for item in results:
        url = item.url.strip()
        title = item.title.strip()
        snippet = item.snippet.strip()
        if not url or not (title or snippet):
            continue
        key = normalize_url(url)
        if key in seen_urls:
            continue
        domain = urlsplit(key).netloc
        if domain_counts.get(domain, 0) >= per_domain:
            continue
        seen_urls.add(key)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        cleaned.append(SearchResult(title=title, url=url, snippet=snippet, content=item.content))
    return cleaned


def select_web_results(
    query: str,
    results: Sequence[SearchResult],
    reranker: Reranker,
    *,
    top_k: int = 3,
    per_domain: int = 2,
) -> list[SearchResult]:
    """Очистить выдачу и оставить top_k наиболее релевантных запросу."""

    cleaned = clean_results(results, per_domain=per_domain)
    if not cleaned:
        return []
    passages = [f"{item.title}. {item.snippet}" for item in cleaned]
    scores = reranker.rerank(query, passages)
    order = sorted(range(len(cleaned)), key=lambda index: (-scores[index], index))
    return [cleaned[index] for index in order[:top_k]]


def format_web_results(results: Sequence[SearchResult]) -> str:
    """Блок результатов поиска для системного промпта."""

    if not results:
        return "(веб-поиск не дал результатов)"
    blocks = []
    for index, item in enumerate(results, 1):
        block = f"[W{index}] {item.title}\n{item.url}\n{item.snippet}"
        if item.content:
            block += f"\nСодержимое страницы:\n{item.content}"
        blocks.append(block)
    return "\n\n".join(blocks)
