# Copyright (C) 2026 AI Trainer contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Конфигурация приложения.

Все настройки читаются из переменных окружения (или `.env`) через
pydantic-settings. Секреты в репозитории не хранятся — только `.env.template`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

type LLMProvider = Literal["ollama", "vllm"]

DISCLAIMER = (
    "Рекомендации носят информационный характер и не заменяют официальные "
    "требования вузов и работодателей."
)


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    # LLM (провайдер не влияет на код: только base_url + model)
    llm_provider: LLMProvider = Field(default="ollama", alias="LLM_PROVIDER")
    llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="qwen2.5:3b-fast", alias="LLM_MODEL")
    llm_api_key: str = Field(default="ollama", alias="LLM_API_KEY")
    llm_temperature: float = Field(default=0.3, alias="LLM_TEMPERATURE")
    llm_request_timeout: float = Field(default=600.0, alias="LLM_REQUEST_TIMEOUT")

    # База данных
    database_url: str = Field(
        default="postgresql+asyncpg://ai_trainer:ai_trainer@localhost:5433/ai_trainer",
        alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")

    # RAG
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL",
    )
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")
    reranker_model: str | None = Field(default=None, alias="RERANKER_MODEL")
    retrieval_top_k: int = Field(default=5, alias="RETRIEVAL_TOP_K")

    # STT
    stt_model: str = Field(default="small", alias="STT_MODEL")
    stt_device: str = Field(default="cpu", alias="STT_DEVICE")
    stt_compute_type: str = Field(default="int8", alias="STT_COMPUTE_TYPE")
    stt_language: str = Field(default="ru", alias="STT_LANGUAGE")

    # Веб-поиск (опционально)
    web_search_enabled: bool = Field(default=False, alias="WEB_SEARCH_ENABLED")
    web_search_cache_ttl: int = Field(default=600, alias="WEB_SEARCH_CACHE_TTL")
    web_search_page_fetch: bool = Field(default=True, alias="WEB_SEARCH_PAGE_FETCH")
    web_search_page_count: int = Field(default=3, alias="WEB_SEARCH_PAGE_COUNT")
    web_fetch_limit: int = Field(default=3, alias="WEB_FETCH_LIMIT")
    web_results_in_context: int = Field(default=2, alias="WEB_RESULTS_IN_CONTEXT")
    web_results_per_domain: int = Field(default=1, alias="WEB_RESULTS_PER_DOMAIN")
    web_page_timeout: float = Field(default=5.0, alias="WEB_PAGE_TIMEOUT")
    web_page_max_chars: int = Field(default=800, alias="WEB_PAGE_MAX_CHARS")

    # Тренажёр
    trainer_cases_max: int = Field(default=5, alias="TRAINER_CASES_MAX")

    # Прочее
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    source_code_url: str = Field(
        default="https://github.com/vladislav-serdyuk/ai-trainer",
        alias="SOURCE_CODE_URL",
    )
    disclaimer: str = DISCLAIMER


@lru_cache
def get_settings() -> Settings:
    """Вернуть единственный экземпляр настроек (кэшируется)."""

    return Settings()
