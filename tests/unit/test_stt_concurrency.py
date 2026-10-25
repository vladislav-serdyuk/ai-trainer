from __future__ import annotations

import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from ai_trainer.stt import transcribe as transcribe_module
from ai_trainer.stt.transcribe import FasterWhisperTranscriber


def test_model_initialized_once_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[object] = []
    barrier = threading.Barrier(2)

    class FakeModel:
        def __init__(self, *args: object, **kwargs: object) -> None:
            created.append(self)
            time.sleep(0.05)

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )
    transcriber = FasterWhisperTranscriber(MagicMock())

    def load() -> object:
        barrier.wait()
        return transcriber._get_model()

    with ThreadPoolExecutor(max_workers=2) as pool:
        models = list(pool.map(lambda _: load(), range(2)))

    assert len(created) == 1
    assert models[0] is models[1]


def test_get_transcriber_returns_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcribe_module, "_transcriber", None)
    monkeypatch.setattr(transcribe_module, "get_settings", lambda: MagicMock())
    barrier = threading.Barrier(8)

    def get() -> object:
        barrier.wait()
        return transcribe_module.get_transcriber()

    with ThreadPoolExecutor(max_workers=8) as pool:
        instances = list(pool.map(lambda _: get(), range(8)))

    assert len({id(instance) for instance in instances}) == 1
