"""Конвертация аудио под STT (ogg/opus → 16 kHz mono WAV) через ffmpeg."""

from __future__ import annotations

import shutil
import subprocess


class AudioConversionError(RuntimeError):
    """Не удалось сконвертировать аудио."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_to_wav(data: bytes, *, sample_rate: int = 16000) -> bytes:
    """Вернуть WAV (16 kHz, mono) из произвольного аудио через ffmpeg."""

    if not ffmpeg_available():
        raise AudioConversionError("ffmpeg не найден")

    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=data,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0 or not process.stdout:
        raise AudioConversionError(process.stderr.decode("utf-8", "ignore")[:300])
    return process.stdout
