# Структура репозитория

Документ объясняет, что где лежит и куда добавлять новый код. Направление
зависимостей слоёв описано в [architecture.md](architecture.md#4-слои-и-правила-зависимостей).

## Дерево

```
корень репы/
├── src/
│   └── ai_trainer/                 # src-layout, имя пакета = ai_trainer
│       ├── __init__.py
│       ├── config.py               # pydantic-settings: env, профили моделей
│       ├── bot/                    # СЛОЙ bot: транспорт aiogram
│       │   ├── main.py             # точка входа (python -m ai_trainer.bot.main)
│       │   ├── handlers/           # хендлеры: команды, текст, голос
│       │   ├── keyboards/          # клавиатуры выбора сценария/режима
│       │   ├── consent.py          # middleware-гейт согласия
│       │   └── deps.py             # сборка зависимостей (синглтоны)
│       ├── pipeline/               # СЛОЙ pipeline: оркестрация диалога
│       │   ├── orchestrator.py     # главный сценарий обработки сообщения
│       │   ├── states.py           # FSM диалога (сценарий/режим/шаг)
│       │   └── context.py          # Reply/Button — транспортно-независимый ответ
│       ├── agent/                  # СЛОЙ agent: LLM и инструменты
│       │   ├── client.py           # LLMClient (openai SDK, provider-agnostic)
│       │   ├── tools/              # retriever, веб-поиск, страницы, чистка/реранк
│       │   └── schemas.py          # pydantic-модели ответов LLM
│       ├── rag/                    # СЛОЙ rag: база знаний
│       │   ├── ingest/             # JSON-источники → chunk → embed → store
│       │   ├── embeddings.py       # fastembed-эмбеддер (см. ADR-0011)
│       │   ├── retrieve.py         # поиск + (опц.) реранк
│       │   └── citations.py        # сборка ссылок на источники
│       ├── stt/                    # СЛОЙ stt (лист)
│       │   ├── transcribe.py       # faster-whisper
│       │   └── audio.py            # ffmpeg: ogg/opus → 16k wav
│       ├── repository/             # СЛОЙ repository: доступ к БД
│       │   ├── models.py           # SQLAlchemy-модели (см. database.md)
│       │   ├── session.py          # async engine/session factory
│       │   └── repos/              # репозитории по сущностям
│       ├── schemas/                # DTO между слоями
│       └── prompts/                # версионируемые промпты (*.md / *.txt)
├── knowledge_base/                 # данные базы знаний (не код)
│   ├── sources/                    # исходные материалы и их метаданные
│   └── seed/                       # сид-данные: кейсы, каталог ошибок, сценарии
├── legal_texts/                    # политика конфиденциальности, EULA
│   ├── pp.md
│   └── eula.md
├── migrations/                     # Alembic
│   ├── env.py
│   └── versions/
├── tests/                          # pytest
│   ├── unit/
│   └── integration/
├── docs/                           # эта документация (+ adr/)
├── .env.template                   # шаблон переменных окружения
├── .gitignore
├── .dockerignore
├── .pre-commit-config.yaml
├── Dockerfile
├── docker-compose.yaml
├── pyproject.toml                  # зависимости, ruff, mypy, pytest
├── README.md
└── LICENSE
```

## Куда что добавлять

| Задача | Куда |
|---|---|
| Новая команда/кнопка бота | `bot/handlers/`, `bot/keyboards/` |
| Изменение логики диалога | `pipeline/orchestrator.py`, `pipeline/states.py` |
| Новый инструмент агента | `agent/tools/` |
| Правка промпта | `prompts/` |
| Новый источник в KB | `knowledge_base/sources/` + ingest |
| Новый сценарий/кейс | `knowledge_base/seed/` + `docs/scenarios.md` |
| Новая таблица/поле | `repository/models.py` + миграция Alembic |
| Новый тип обращения к БД | `repository/repos/` |

## Правила

- **src-layout**: импорты только `ai_trainer.*`, относительных «прыжков» нет.
- **Слои вниз, не вверх**: см. ADR-[0009](adr/0009-layered-architecture-and-ports.md).
  Например, `rag/` не импортирует `bot/`.
- **Промпты — в файлах**, не строковые литералы в коде: их ревьюят и
  версионируют.
- **Секреты — только в `.env`**, репозиторий содержит лишь `.env.template`.
- **Секреты и данные KB не коммитим**, если у источника нет открытой лицензии
  (см. ADR-[0010](adr/0010-ethics-and-data-minimization.md)).
