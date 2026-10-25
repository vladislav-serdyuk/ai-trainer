"""Загрузка текста страниц найденных результатов (обогащение live-контекста)."""

from __future__ import annotations

import asyncio
import logging
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer"}
_BLOCK_TAGS = {
    "address",
    "article",
    "blockquote",
    "br",
    "div",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
}
_MAX_BYTES = 400_000
_CACHE_MAX = 512
_USER_AGENT = "Mozilla/5.0 (compatible; ai-trainer/0.1; +https://example.org)"


class _TextExtractor(HTMLParser):
    """Простейший HTML→текст без внешних зависимостей."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip > 0:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def extract_text(html: str) -> str:
    """Вырезать читаемый текст: без script/style, с нормализацией пробелов."""

    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Повреждённый html не должен ломать загрузку.
        pass
    lines = [" ".join(line.split()) for line in unescape(parser.text()).splitlines()]
    return "\n".join(line for line in lines if line)


def _download(url: str, timeout: float) -> str:
    request = Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "ru,en;q=0.8"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw: bytes = response.read(_MAX_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="ignore")


class WebPageLoader:
    """Текст страницы по url с TTL-кэшем; при сбое — пустая строка."""

    def __init__(
        self, *, timeout: float = 8.0, max_chars: int = 2000, ttl_seconds: float = 600
    ) -> None:
        self._timeout = timeout
        self._max_chars = max_chars
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, str]] = {}

    async def load(self, url: str) -> str:
        now = time.monotonic()
        cached = self._cache.get(url)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        text: str = await asyncio.to_thread(self._load_sync, url)
        if text:
            self._prune(now)
            self._cache[url] = (now, text)
        return text

    def _load_sync(self, url: str) -> str:
        if urlsplit(url).scheme not in {"http", "https"}:
            return ""
        try:
            html = _download(url, self._timeout)
        except Exception as exc:
            # Страница может блокировать бота — не роняем диалог.
            logger.info("page fetch failed %s: %s", url, exc)
            return ""
        text = extract_text(html)
        if len(text) > self._max_chars:
            text = text[: self._max_chars].rsplit(" ", 1)[0] + "…"
        return text

    def _prune(self, now: float) -> None:
        if len(self._cache) < _CACHE_MAX:
            return
        expired = [url for url, (stamp, _) in self._cache.items() if now - stamp >= self._ttl]
        for url in expired:
            del self._cache[url]
        if len(self._cache) >= _CACHE_MAX:
            oldest = min(self._cache, key=lambda url: self._cache[url][0])
            del self._cache[oldest]
