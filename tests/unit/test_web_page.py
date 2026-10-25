from __future__ import annotations

import pytest

from ai_trainer.agent.tools import web_page
from ai_trainer.agent.tools.web_cleanup import format_web_results
from ai_trainer.agent.tools.web_page import WebPageLoader, extract_text
from ai_trainer.agent.tools.web_search import SearchResult


def test_extract_text_strips_scripts_styles_and_tags() -> None:
    html = (
        "<html><head><style>p{color:red}</style></head>"
        "<body><script>var x=1;</script><h1>Курс</h1>"
        "<p>Доллар&nbsp;— 95,5&nbsp;₽</p></body></html>"
    )

    text = extract_text(html)

    assert "var x" not in text
    assert "color:red" not in text
    assert "Курс" in text
    assert "Доллар — 95,5 ₽" in text


@pytest.mark.asyncio
async def test_web_page_loader_caches_and_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_download(url: str, timeout: float) -> str:
        nonlocal calls
        calls += 1
        return "<html><body><p>" + ("слово " * 1000) + "</p></body></html>"

    monkeypatch.setattr(web_page, "_download", fake_download)
    loader = WebPageLoader(timeout=1.0, max_chars=50, ttl_seconds=600)

    first = await loader.load("https://example.org/a")
    second = await loader.load("https://example.org/a")

    assert first == second
    assert first.endswith("…")
    assert len(first) <= 51
    assert calls == 1


@pytest.mark.asyncio
async def test_web_page_loader_returns_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float) -> str:
        raise OSError("blocked")

    monkeypatch.setattr(web_page, "_download", boom)
    loader = WebPageLoader()

    assert await loader.load("https://example.org/a") == ""


def test_format_web_results_includes_page_content() -> None:
    results = [
        SearchResult("Заголовок", "https://a.ru/1", "снипет", content="Доллар 95,5"),
        SearchResult("Второй", "https://b.ru/1", "снипет"),
    ]

    block = format_web_results(results)

    assert "Содержимое страницы:\nДоллар 95,5" in block
    assert "[W2] Второй" in block
    assert format_web_results([]) == "(веб-поиск не дал результатов)"
