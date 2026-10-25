"""Провайдеро-независимый клиент LLM (Ollama / vLLM через OpenAI SDK).

См. ADR-0003 (миграция через конфиг) и ADR-0008 (структурированный вывод).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from openai import AsyncOpenAI, BadRequestError, OpenAIError

from ai_trainer.agent.tools.base import ToolSpec
from ai_trainer.config import Settings, get_settings

MAX_TOOL_ROUNDS = 3
MAX_SCHEMA_RETRIES = 1

type Message = dict[str, Any]

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "LLMError", "LLMOutputError"]


class LLMError(RuntimeError):
    """Ошибка запроса к LLM."""


class LLMOutputError(LLMError):
    """LLM вернул ответ, который не удалось привести к схеме."""


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = AsyncOpenAI(
            base_url=self._settings.llm_base_url,
            api_key=self._settings.llm_api_key,
            timeout=self._settings.llm_request_timeout,
        )

    # -- helpers -----------------------------------------------------------

    def _response_format(self, schema: type[Any]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": False,
            },
        }

    async def _create(
        self, messages: list[Message], *, schema: type[Any] | None, tools: list[ToolSpec] | None
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": cast(Any, messages),
            "temperature": self._settings.llm_temperature,
        }
        if self._settings.llm_provider == "ollama":
            # thinking-токены qwen3 утекают в content и ломают structured
            # output (интермиттентно); для наших задач мышление не нужно.
            kwargs["extra_body"] = {"think": False}
        try:
            if tools:
                kwargs["tools"] = [tool.to_openai() for tool in tools]
                kwargs["tool_choice"] = "auto"
                # NB: Ollama игнорирует tools при response_format — JSON по схеме
                # запрашиваем промптом, а строгий формат добираем финальным ретраем
                # в _complete (без инструментов).
            elif schema is not None:
                kwargs["response_format"] = cast(Any, self._response_format(schema))
                try:
                    return await self._client.chat.completions.create(**kwargs)
                except BadRequestError as exc:
                    # Провайдер не поддерживает response_format — просим JSON в промпте.
                    logger.warning("response_format отклонён (%s), fallback на промпт", exc)
                    kwargs.pop("response_format", None)
                    messages.append(
                        {
                            "role": "system",
                            "content": "Отвечай СТРОГО валидным JSON без текста вокруг.",
                        }
                    )
            return await self._client.chat.completions.create(**kwargs)
        except BadRequestError:
            raise
        except OpenAIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

    # -- public API --------------------------------------------------------

    async def chat_text(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        tool_dispatch: dict[str, Any] | None = None,
    ) -> str:
        """Свободный текстовый ответ (опционально с инструментами)."""

        return await self._complete(messages, schema=None, tools=tools, tool_dispatch=tool_dispatch)

    async def chat_json(
        self,
        messages: list[Message],
        schema: type[Any],
        *,
        tools: list[ToolSpec] | None = None,
        tool_dispatch: dict[str, Any] | None = None,
    ) -> Any:
        """Ответ LLM, приведённый к pydantic-схеме."""

        current = list(messages)
        retries = 0
        while True:
            try:
                content = await self._complete(
                    current, schema=schema, tools=tools, tool_dispatch=tool_dispatch
                )
                return self._validate(content, schema)
            except LLMOutputError as exc:
                if retries >= MAX_SCHEMA_RETRIES:
                    raise
                logger.warning("LLM output validation failed (%s), retrying...", exc)
                current.append({"role": "assistant", "content": str(exc)})
                current.append(
                    {
                        "role": "user",
                        "content": (
                            "Твой предыдущий ответ не был валидным JSON по требуемой схеме. "
                            "Ответь СТРОГО валидным JSON без лишнего текста."
                        ),
                    }
                )
                retries += 1
                tools = None
                tool_dispatch = None

    async def _complete(
        self,
        messages: list[Message],
        *,
        schema: type[Any] | None,
        tools: list[ToolSpec] | None,
        tool_dispatch: dict[str, Any] | None,
    ) -> str:
        current = list(messages)
        tool_rounds = 0

        while True:
            response = await self._create(current, schema=schema, tools=tools)
            choice = response.choices[0]
            message = choice.message

            tool_calls = message.tool_calls
            if tool_calls and tool_dispatch and tool_rounds < MAX_TOOL_ROUNDS:
                current.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )
                for tool_call in tool_calls:
                    result = await self._invoke_tool(tool_call, dispatch=tool_dispatch)
                    current.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )
                tool_rounds += 1
                continue

            content = message.content or ""
            if schema is not None and tools and not self._fits(content, schema):
                # Ollama не совмещает tools и response_format: если по промпту
                # JSON не собрался — финализируем строгим форматом уже без
                # инструментов, сохраняя в истории результаты вызовов.
                final = await self._create(current, schema=schema, tools=None)
                content = final.choices[0].message.content or ""
            return content

    @staticmethod
    def _fits(content: str, schema: type[Any]) -> bool:
        try:
            schema.model_validate(json.loads(_extract_json(content)))
        except Exception:
            return False
        return True

    async def _invoke_tool(self, tool_call: Any, dispatch: dict[str, Any]) -> str:
        name = tool_call.function.name
        logger.info("LLM tool call: %s(%s)", name, tool_call.function.arguments)
        handler = dispatch.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False)
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        try:
            return str(await handler(args))
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def _validate(self, content: str, schema: type[Any]) -> Any:
        try:
            data = json.loads(_extract_json(content))
        except json.JSONDecodeError as exc:
            raise LLMOutputError(f"ответ LLM не является JSON: {content[:200]}") from exc
        try:
            return schema.model_validate(data)
        except Exception as exc:
            raise LLMOutputError(f"ответ LLM не прошёл валидацию: {exc}") from exc


def _extract_json(content: str) -> str:
    """Извлечь JSON, если модель добавила текст вокруг него."""

    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text
