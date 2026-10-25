"""Транспортно-независимые типы ответа оркестратора.

Бизнес-логика описывает ответ текстом и кнопками; слой бота рендерит это в
aiogram. Так pipeline не импортирует bot (см. ADR-0009).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Button:
    text: str
    data: str


@dataclass(slots=True)
class Reply:
    text: str
    keyboard: list[list[Button]] = field(default_factory=list)
    show_menu_button: bool = True

    @property
    def flat_buttons(self) -> list[Button]:
        return [button for row in self.keyboard for button in row]


def inline(*buttons: Button) -> list[list[Button]]:
    return [[button] for button in buttons]
