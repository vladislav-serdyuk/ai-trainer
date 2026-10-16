# Журнал архитектурных решений (ADR)

Здесь фиксируются значимые архитектурные решения проекта в формате
[Architecture Decision Record](https://adr.github.io/). Каждое решение — отдельный
файл, чтобы был виден контекст и последствия, а не только итоговый выбор.

## Правила

- Формат имени файла: `NNNN-kratkoe-nazvanie.md` (например,
  `0007-python-3-12.md`).
- Шаблон: [template.md](template.md).
- Статусы: `Proposed`, `Accepted`, `Deprecated`, `Superseded by NNNN`.
- Не редактируйте содержание принятого ADR задним числом, кроме смены статуса.
  Новое решение оформляйте новым ADR и помечайте старое как `Superseded`.
- Решения с обратной силой (задним числом по уже принятому) оформляются как новый
  ADR.

## Индекс

| № | Решение | Статус |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Вести журнал архитектурных решений | Accepted |
| [0002](0002-telegram-bot-aiogram.md) | Telegram-бот как транспорт, aiogram | Accepted |
| [0003](0003-local-llm-ollama-then-vllm.md) | Локальная LLM: Ollama со стартом, миграция на vLLM | Accepted |
| [0004](0004-stt-faster-whisper-cpu.md) | STT на faster-whisper, работа на CPU | Accepted |
| [0005](0005-rag-pgvector.md) | RAG на PostgreSQL + pgvector | Accepted |
| [0006](0006-web-search-duckduckgo.md) | Веб-поиск через duckduckgo_search за абстракцией | Accepted |
| [0007](0007-python-3-12.md) | Фиксируем Python 3.12 | Accepted |
| [0008](0008-structured-llm-output.md) | Структурированный вывод LLM + валидация pydantic | Accepted |
| [0009](0009-layered-architecture-and-ports.md) | Слоистая архитектура и правила зависимостей | Accepted |
| [0010](0010-ethics-and-data-minimization.md) | Этика, дисклеймер, минимизация ПДн | Accepted |
