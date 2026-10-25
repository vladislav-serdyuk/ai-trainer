"""Разбиение текста на чанки для RAG."""

from __future__ import annotations

import re

_MAX_PARAGRAPH_OVERRUN = 0


def chunk_text(text: str, *, max_chars: int = 900) -> list[str]:
    """Разбить текст на чанки ~max_chars символов.

    Основан на абзацах; очень длинные абзацы режутся по символам.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        piece = paragraph
        while len(piece) > max_chars:
            head, piece = piece[:max_chars], piece[max_chars:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head.strip())

        if not current:
            current = piece
        elif len(current) + 2 + len(piece) <= max_chars + _MAX_PARAGRAPH_OVERRUN:
            current += f"\n\n{piece}"
        else:
            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)
    return [c for c in chunks if c]


def approximate_token_count(text: str) -> int:
    """Грубая оценка числа токенов (для статистики)."""

    return max(1, len(text) // 4)
