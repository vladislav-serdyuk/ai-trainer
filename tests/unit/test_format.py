from __future__ import annotations

import pytest

from ai_trainer.pipeline.format import trainer_mode_text


@pytest.mark.parametrize(
    ("count", "phrase"),
    [
        (1, "1 проблемный кейс"),
        (2, "2 проблемных кейса"),
        (4, "4 проблемных кейса"),
        (5, "5 проблемных кейсов"),
        (11, "11 проблемных кейсов"),
        (21, "21 проблемный кейс"),
        (22, "22 проблемных кейса"),
    ],
)
def test_trainer_mode_text_pluralizes_cases(count: int, phrase: str) -> None:
    assert phrase in trainer_mode_text("Поиск работы", count)
