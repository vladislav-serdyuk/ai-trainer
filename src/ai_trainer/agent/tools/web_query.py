"""Переформулировка вопроса пользователя в короткий поисковый запрос."""

from __future__ import annotations

from pydantic import BaseModel

from ai_trainer.agent.client import LLMClient

_REWRITE_SYSTEM = (
    "Преврати вопрос пользователя в короткий поисковый запрос для интернета: "
    "3–7 слов, только ключевые термины, без вежливости и вводных слов. "
    "Не добавляй того, чего нет в вопросе. Верни только JSON по схеме."
)


class SearchQuery(BaseModel):
    query: str


async def rewrite_search_query(llm: LLMClient, question: str) -> str:
    """Короткий поисковый запрос; при сбое — исходный текст вопроса."""

    try:
        result: SearchQuery = await llm.chat_json(
            [
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": question},
            ],
            SearchQuery,
        )
    except Exception:
        return question
    query = result.query.strip()
    return query or question
