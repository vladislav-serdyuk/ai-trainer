"""Форматирование ответов для показа пользователю."""

from __future__ import annotations

from collections.abc import Sequence

from ai_trainer.agent.schemas import Citation, InfoAnswer, TrainerEvaluation
from ai_trainer.config import get_settings
from ai_trainer.repository.enums import Verdict
from ai_trainer.repository.models import Case, CaseAnswer, Scenario

_VERDICT_LABEL = {
    Verdict.correct: "✅ Это верно",
    Verdict.partial: "🟡 В основном верно",
    Verdict.incorrect: "❌ Пока не так",
}


def disclaimer() -> str:
    return f"\n\n*{get_settings().disclaimer}*"


def menu_text() -> str:
    return "Выбери сценарий, по которому потренируемся:"


def about_text() -> str:
    return (
        "Я — AI-тренажёр для абитуриентов и начинающих специалистов: помогаю "
        "разобраться с выбором вуза или профессии, найти первую работу и "
        "пережить первые месяцы на новом месте.\n\n"
        "Два режима:\n"
        "• *Справочник* — задай вопрос текстом или голосом; отвечу по проверенной "
        "базе знаний и веб-поиску и покажу источники.\n"
        "• *Тренажёр* — дам проблемный кейс; после твоего ответа скажу, что "
        "улучшить, приведу удачный пример и отмечу типовые ошибки."
    )


def help_text() -> str:
    return (
        "Как пользоваться ботом:\n\n"
        "1. Выбери сценарий в меню (вузы, первая работа, первый месяц).\n"
        "2. «Справочник» — задавай вопросы текстом или голосом. Отвечу по базе "
        "знаний и веб-поиску и всегда покажу источники.\n"
        "3. «Тренажёр» — отвечай на проблемные кейсы; я разберу ответ: оценка, "
        "что улучшить, удачный пример и типовые ошибки.\n\n"
        "Команды:\n"
        "/start — начать заново\n"
        "/menu — меню сценариев\n"
        "/help — эта справка\n"
        "/stop — завершить текущую сессию\n"
        "/delete — удалить мои данные\n\n"
        "Голосовые сообщения распознаются автоматически. Рекомендации носят "
        "информационный характер и не заменяют официальные требования вузов "
        "и работодателей."
    )


def scenario_text(scenario: Scenario) -> str:
    return f"Сценарий: {scenario.title}.\nВыбери режим:"


def info_mode_text(scenario_title: str | None) -> str:
    where = f" по сценарию «{scenario_title}»" if scenario_title else ""
    return f"Режим справочника{where}. Задавай вопросы текстом или голосом."


def _case_count_phrase(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} проблемный кейс"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} проблемных кейса"
    return f"{count} проблемных кейсов"


def trainer_mode_text(scenario_title: str | None, case_count: int) -> str:
    where = f" по сценарию «{scenario_title}»" if scenario_title else ""
    return f"Режим тренажёра{where}. Тебе дам {_case_count_phrase(case_count)}. Начнём?"


def case_prompt_text(case: Case, index: int, total: int) -> str:
    return (
        f"Кейс {index + 1} из {total} · {case.title}\n\n"
        f"{case.prompt}\n\n"
        "Отвечай текстом или голосом — разберу ответ и скажу, что улучшить."
    )


def citations_text(citations: Sequence[Citation]) -> str:
    lines = ["Источники:"]
    for i, c in enumerate(citations, 1):
        title = c.title or c.url or "источник"
        url = c.url
        lines.append(f"{i}. {title}" + (f" — {url}" if url else ""))
    return "\n".join(lines)


def info_reply_text(answer: InfoAnswer) -> str:
    parts = [answer.answer.strip()]
    if answer.citations:
        parts.append(citations_text(answer.citations))
    return "\n\n".join(parts) + disclaimer()


def feedback_text(
    evaluation: TrainerEvaluation,
    case: Case,
    index: int,
    total: int,
    mistake_descriptions: Sequence[str] | None = None,
) -> str:
    verdict = _VERDICT_LABEL.get(evaluation.verdict, "Оценка")
    lines = [
        f"Кейс {index + 1} из {total} · {case.title}",
        "",
        verdict,
    ]
    if evaluation.score is not None:
        lines.append(f"Оценка: {evaluation.score}/100")
    if evaluation.what_to_improve:
        lines += ["", "Вот что можно улучшить:", evaluation.what_to_improve]
    if evaluation.example_answer:
        lines += ["", "Вот удачный пример ответа:", evaluation.example_answer]
    if mistake_descriptions:
        lines += ["", "Типовые ошибки, которые заметил:"] + [f"- {d}" for d in mistake_descriptions]
    elif evaluation.detected_mistakes:
        mistakes = [m.replace("_", " ") for m in evaluation.detected_mistakes]
        lines += ["", "Типовые ошибки, которые заметил: " + ", ".join(mistakes)]
    if evaluation.citations:
        lines += ["", citations_text(evaluation.citations)]
    return "\n".join(lines) + disclaimer()


def summary_text(summary: str, answers: Sequence[CaseAnswer]) -> str:
    correct = sum(1 for a in answers if a.verdict == Verdict.correct)
    partial = sum(1 for a in answers if a.verdict == Verdict.partial)
    incorrect = sum(1 for a in answers if a.verdict == Verdict.incorrect)
    header = (
        f"Итог сессии: верно {correct}, частично {partial}, неверно {incorrect} из {len(answers)}."
    )
    return "\n\n".join([header, summary.strip()]) + disclaimer()


def unknown_state_text() -> str:
    return "Что-то пошло не так — вернёмся в меню."


def error_text() -> str:
    return "Не получилось получить ответ. Попробуй ещё раз чуть позже."
