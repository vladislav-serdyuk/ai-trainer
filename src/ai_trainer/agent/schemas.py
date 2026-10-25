"""Структурированные схемы ответов LLM (ADR-0008)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_trainer.repository.enums import Verdict


class Citation(BaseModel):
    """Ссылка на источник, которую показывает пользователю бот."""

    document_id: int | None = None
    url: str | None = None
    title: str | None = None
    source_type: str | None = None
    quote: str | None = None


class InfoAnswer(BaseModel):
    """Ответ информационного режима."""

    answer: str = Field(description="Содержательный ответ пользователю")
    citations: list[Citation] = Field(default_factory=list)


class TrainerEvaluation(BaseModel):
    """Оценка ответа в режиме тренажёра (Этап 3)."""

    verdict: Verdict = Field(description="correct | partial | incorrect")
    score: int | None = Field(default=None, ge=0, le=100)
    what_to_improve: str = Field(description="«Вот что можно улучшить»")
    example_answer: str = Field(description="«Вот удачный пример ответа»")
    detected_mistakes: list[str] = Field(
        default_factory=list, description="Коды ошибок из каталога ошибок"
    )
    citations: list[Citation] = Field(default_factory=list)
