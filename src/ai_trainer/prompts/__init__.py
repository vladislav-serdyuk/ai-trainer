"""Загрузка версионируемых промптов из файлов (а не строк в коде)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def load_prompt(name: str) -> str:
    """Прочитать промпт по имени файла (без расширения), например 'persona'."""

    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").strip()
