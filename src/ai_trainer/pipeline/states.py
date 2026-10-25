"""Схема callback-данных и данные FSM (см. architecture.md §5.2)."""

from __future__ import annotations

PREFIX_SCENARIO = "sc"
PREFIX_MODE = "md"
PREFIX_MENU = "menu"
PREFIX_CONSENT = "consent"
PREFIX_STOP = "stop"


def scenario_cb(scenario_code: str) -> str:
    return f"{PREFIX_SCENARIO}:{scenario_code}"


def mode_cb(mode: str) -> str:
    return f"{PREFIX_MODE}:{mode}"


MENU_CB = PREFIX_MENU
CONSENT_CB = PREFIX_CONSENT
STOP_CB = PREFIX_STOP


def parse_callback(data: str) -> tuple[str, str]:
    """Разобрать callback_data в (prefix, value)."""

    if ":" in data:
        prefix, value = data.split(":", 1)
        return prefix, value
    return data, ""
