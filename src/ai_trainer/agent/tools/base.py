"""Спецификация инструмента (function calling) для агента."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass(slots=True)
class ToolSpec:
    """Инструмент в формате OpenAI function-calling."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
