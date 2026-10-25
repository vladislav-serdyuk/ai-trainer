"""Перечисления предметной области.

Значения совпадают с именами и хранятся в БД как строки (см.
`docs/database.md`).
"""

from __future__ import annotations

from enum import Enum, StrEnum


class Mode(StrEnum):
    informational = "informational"
    trainer = "trainer"


class SessionState(StrEnum):
    idle = "idle"
    choose_scenario = "choose_scenario"
    choose_mode = "choose_mode"
    qa_loop = "qa_loop"
    case_loop = "case_loop"
    feedback = "feedback"
    summary = "summary"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ContentType(StrEnum):
    text = "text"
    voice = "voice"


class Verdict(StrEnum):
    correct = "correct"
    partial = "partial"
    incorrect = "incorrect"


class SourceType(StrEnum):
    official = "official"
    review = "review"
    media = "media"
    academic = "academic"
    forum = "forum"


def enum_values(enum_cls: type[Enum]) -> list[str]:
    """Значения enum для хранения в БД (порядок — как объявлен)."""

    return [member.value for member in enum_cls]
