# Разработка

Про окружение, инструменты и договорённости. Для новых участников — читать после
[architecture.md](architecture.md) и [repository-structure.md](repository-structure.md).

## Требования

- **Python 3.12** (см. [ADR-0007](adr/0007-python-3-12.md)). Системный 3.14 не
  используем.
- **uv** — управление окружением и зависимостями.
- **Docker + Docker Compose** — PostgreSQL + pgvector.
- **ffmpeg** — конвертация голосовых для STT.
- **Ollama** — локальная LLM (см. [ADR-0003](adr/0003-local-llm-ollama-then-vllm.md)).
- GPU: NVIDIA RTX 4050 Laptop, 6 GB VRAM.

## Первый запуск (черновик, уточняется по мере реализации)

```bash
# 1. Окружение Python 3.12
uv python install 3.12
uv sync

# 2. Переменные окружения
cp .env.template .env   # заполнить токен бота и провайдера LLM

# 3. БД
docker compose up -d db

# 4. Миграции
uv run alembic upgrade head

# 5. Загрузка базы знаний (сид + ingest)
uv run python -m ai_trainer.rag.ingest

# 6. Локальная модель
ollama pull qwen2.5:3b

# 7. Запуск бота
uv run python -m ai_trainer.bot.main
```

## Инструменты качества

| Инструмент | Назначение | Команда |
|---|---|---|
| ruff | линт и формат | `uv run ruff check .` / `uv run ruff format .` |
| mypy | типы, `--strict` | `uv run mypy src` |
| pytest | тесты | `uv run pytest` |
| pre-commit | запуск проверок перед коммитом | `uv run pre-commit install` |

Все проверки прогоняются в pre-commit hook. Коммит не проходит, пока не
выполнены ruff/mypy. См. [ADR-0009](adr/0009-layered-architecture-and-ports.md)
и конвенции ниже.

## Конвенции кода

- **Типизация обязательна**, `mypy --strict`. Публичные функции — с аннотациями.
- **Async**: работа с БД и сетью — асинхронная (SQLAlchemy 2.x async, aiogram 3,
  httpx).
- **Без комментариев в коде**, если они не объясняют неочевидное «почему».
  Понятные имена вместо комментариев.
- **Промпты — в `src/ai_trainer/prompts/`**, не в виде строк в коде.
- **Секреты — только в `.env`**; в репозиторий попадает лишь `.env.template`.
- **Слои не импортируют вверх** (см. ADR-0009).

## Работа с базой знаний

- Исходники и метаданные — в `knowledge_base/sources/`, сид-данные (кейсы,
  ошибки, сценарии) — в `knowledge_base/seed/`.
- У каждого источника обязательны `url`, тип, дата обращения и лицензия.
- База знаний и результаты инференса не коммитятся; в репозиторий попадают только
  открытые материалы с корректной лицензией.

## Git

- Ветки от `main`, PR с описанием изменения и ссылкой на ADR, если решение
  архитектурное.
- Коммит содержит одну логическую единицу.
- **Сообщения коммитов — по [Conventional Commits](https://www.conventionalcommits.org/):**
  `<type>(<scope>): <описание>` в повелительном наклонении.
  - Типы: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`,
    `perf`, `style`.
  - Пример: `feat(agent): add structured output validation`,
    `docs(adr): record STT decision`.
- Архитектурное изменение без нового/обновлённого ADR не принимается.
