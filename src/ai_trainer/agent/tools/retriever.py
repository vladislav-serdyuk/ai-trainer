"""Инструмент ретрива по базе знаний (function calling)."""

from __future__ import annotations

import json
from typing import Any

from ai_trainer.agent.tools.base import ToolSpec
from ai_trainer.rag.retrieve import Retriever

RETRIEVER_TOOL_NAME = "search_knowledge_base"

_RETRIEVER_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Запрос для поиска в базе знаний",
        }
    },
    "required": ["query"],
}


def build_retriever_tool(
    retriever: Retriever, *, scenario_code: str | None, top_k: int = 5
) -> ToolSpec:
    async def handler(args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return json.dumps({"results": []}, ensure_ascii=False)
        chunks = await retriever.search(query, scenario_code=scenario_code, top_k=top_k)
        payload = [
            {
                "title": c.title,
                "url": c.url,
                "source_type": c.source_type.value,
                "quote": c.content,
            }
            for c in chunks
        ]
        return json.dumps({"results": payload}, ensure_ascii=False)

    return ToolSpec(
        name=RETRIEVER_TOOL_NAME,
        description=(
            "Поиск релевантных фрагментов в базе знаний по текстовому запросу. "
            "Используй, чтобы подкрепить ответ фактами из источников."
        ),
        parameters=_RETRIEVER_PARAMETERS,
        handler=handler,
    )
