"""Локальный STT на faster-whisper (int8, по умолчанию CPU) — ADR-0004."""

from __future__ import annotations

import io
import threading
from typing import Protocol, runtime_checkable

from ai_trainer.config import Settings, get_settings
from ai_trainer.stt.audio import AudioConversionError, convert_to_wav

_transcriber: FasterWhisperTranscriber | None = None
_transcriber_lock = threading.Lock()


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio: bytes) -> str:
        """Распознать речь в тексте (синхронно; вызывать в отдельном потоке)."""
        ...


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: object | None = None
        self._model_lock = threading.Lock()

    def _get_model(self) -> object:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._settings.stt_model,
                    device=self._settings.stt_device,
                    compute_type=self._settings.stt_compute_type,
                )
            return self._model

    def transcribe(self, audio: bytes) -> str:
        source = audio
        try:
            source = convert_to_wav(audio)
        except AudioConversionError:
            # faster-whisper умеет декодировать ogg/opus сам — работаем без ffmpeg.
            pass

        model = self._get_model()
        segments, _info = model.transcribe(  # type: ignore[attr-defined]
            io.BytesIO(source),
            language=self._settings.stt_language,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class FakeTranscriber:
    """Заглушка для тестов."""

    def __init__(self, text: str = "тестовый ответ") -> None:
        self._text = text

    def transcribe(self, audio: bytes) -> str:
        return self._text


def get_transcriber() -> Transcriber:
    """Единственный экземпляр транскрайбера (ленивая инициализация модели)."""

    global _transcriber
    if _transcriber is not None:
        return _transcriber
    with _transcriber_lock:
        if _transcriber is None:
            _transcriber = FasterWhisperTranscriber(get_settings())
        return _transcriber
