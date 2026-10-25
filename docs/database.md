# Модель данных

СУБД — **PostgreSQL + pgvector** ([ADR-0005](adr/0005-rag-pgvector.md)). Модели —
SQLAlchemy 2.x (async), миграции — Alembic. Ниже перечислены сущности, их поля и
связи.

## Обзор связей

```
users 1───* sessions 1───* messages
                  │
                  ├─── scenario (scenarios)
                  └───* case_answers ──* cases ── scenario
                                          │
                                          *─── mistake_catalog (ссылка по коду)

documents 1───* chunks (embedding vector(384))
documents.scenario ── scenarios.code   (логическая связь по коду сценария)
```

## Перечисления (enum)

| Enum | Значения |
|---|---|
| `mode` | `informational`, `trainer` |
| `session_state` | `idle`, `choose_scenario`, `choose_mode`, `qa_loop`, `case_loop`, `feedback`, `summary` |
| `message_role` | `user`, `assistant`, `system` |
| `content_type` | `text`, `voice` |
| `verdict` | `correct`, `partial`, `incorrect` |
| `source_type` | `official`, `review`, `media`, `academic`, `forum` |

## users

Пользователь Telegram. Персональных данных минимум (см.
[ADR-0010](adr/0010-ethics-and-data-minimization.md)).

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | внутренний идентификатор |
| `telegram_id` | bigint, unique, not null | id пользователя в Telegram |
| `consent_at` | timestamptz, null | момент согласия с EULA/политикой |
| `created_at` | timestamptz, not null | дата регистрации |
| `deleted_at` | timestamptz, null | soft-delete по `/delete` |

## scenarios

Справочник сценариев (заполняется сид-данными).

| Поле | Тип | Описание |
|---|---|---|
| `code` | text PK | `university_choice`, `job_search`, `first_month` |
| `title` | text, not null | человекочитаемое название |
| `description` | text | краткое описание |
| `sort_order` | int | порядок в меню |

## sessions

Одна сессия диалога по выбранному сценарию и режиму.

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | — |
| `user_id` | bigint FK → users | владелец |
| `scenario_code` | text FK → scenarios, null | выбранный сценарий (null до выбора) |
| `mode` | `mode`, null | режим (null до выбора) |
| `state` | `session_state`, not null | текущее состояние FSM |
| `case_ids` | jsonb, not null, default `[]` | выбранные кейсы тренажёра (до `TRAINER_CASES_MAX`, но не больше доступных) |
| `case_index` | int, not null, default `0` | позиция в наборе кейсов |
| `started_at` | timestamptz, not null | начало |
| `last_activity_at` | timestamptz, not null | последняя активность (диагностика; idle-таймаут не применяется) |
| `ended_at` | timestamptz, null | завершение (null = активная) |

Индексы:
- `(user_id, started_at)`;
- **частичный уникальный** `unique(user_id) where ended_at is null` — не более
  одной активной сессии на пользователя.

Состояние (`scenario_code`, `mode`, прогресс) считаем источником истины для
восстановления после перезапуска бота; FSM aiogram хранит только эфемерные
флаги «жду ввод». См. [architecture.md](architecture.md#5-компоненты).

## messages

История сообщений сессии (текст и расшифровка голоса).

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | — |
| `session_id` | bigint FK → sessions | — |
| `role` | `message_role`, not null | автор |
| `content_type` | `content_type`, not null | текстом или голосом |
| `content` | text, not null | текст (для голоса — расшифровка) |
| `citations` | jsonb, null | ссылки на источники ответа |
| `created_at` | timestamptz, not null | — |

Индексы: `(session_id, created_at)`.

## cases

Банк проблемных кейсов для режима тренажёра. **Структурированные записи, а не
векторный поиск** — см. [scenarios.md](scenarios.md).

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | — |
| `code` | text, unique | стабильный код кейса |
| `scenario_code` | text FK → scenarios | принадлежность сценарию |
| `title` | text, not null | краткий заголовок |
| `prompt` | text, not null | вопрос/ситуация пользователю |
| `difficulty` | smallint | 1–3 |
| `expected_points` | jsonb, not null | ключевые пункты хорошего ответа |
| `exemplary_answer` | text, not null | «удачный пример ответа» |
| `mistake_codes` | jsonb | типовые ошибки, релевантные кейсу |
| `document_ids` | jsonb | источники KB для заземления |
| `sort_order` | int | порядок выдачи |

Индексы: `(scenario_code, sort_order)`.

## case_answers

Результат разбора ответа пользователя (реализует Этап 3).

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | — |
| `session_id` | bigint FK → sessions | — |
| `case_id` | bigint FK → cases | — |
| `user_answer` | text, not null | ответ пользователя |
| `verdict` | `verdict`, not null | «это верно»: correct/partial/incorrect |
| `score` | smallint, null | опциональная оценка 0–100 |
| `what_to_improve` | text | «вот что можно улучшить» |
| `example_answer` | text | «вот удачный пример ответа» |
| `detected_mistakes` | jsonb | коды ошибок из `mistake_catalog` |
| `citations` | jsonb | ссылки на источники |
| `created_at` | timestamptz, not null | — |

Индексы: `(session_id)`, `(case_id)`.

> Точки расширения Этапа 4: агрегация `detected_mistakes` по `user_id` даёт
> профиль слабых зон. Отдельная таблица не заводится, пока этап не в объёме.

## mistake_catalog

Каталог типовых ошибок (курируемый, глобальный — не per-user).

| Поле | Тип | Описание |
|---|---|---|
| `code` | text PK | код ошибки |
| `scenario_code` | text FK → scenarios, null | сценарий или общая |
| `description` | text, not null | как звучит ошибка |
| `trigger_examples` | jsonb | примеры фраз-триггеров |
| `improved_wording` | text | улучшенная формулировка |
| `example_answer` | text | удачный пример |
| `document_ids` | jsonb | источники KB |

## documents

Источник базы знаний с метаданными (для цитирования).

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | — |
| `scenario_code` | text FK → scenarios, null | сценарий или общий источник |
| `title` | text, not null | заголовок |
| `url` | text, not null | ссылка |
| `source_type` | `source_type`, not null | тип источника |
| `author` | text, null | автор/издание |
| `license` | text, null | лицензия/условия использования |
| `accessed_at` | date, not null | дата обращения |
| `meta` | jsonb | прочие атрибуты |
| `created_at` | timestamptz, not null | — |

## chunks

Фрагмент документа с эмбеддингом для векторного поиска.

| Поле | Тип | Описание |
|---|---|---|
| `id` | bigint PK | — |
| `document_id` | bigint FK → documents | — |
| `chunk_index` | int, not null | порядок внутри документа |
| `content` | text, not null | текст чанка |
| `token_count` | int | размер |
| `embedding` | `vector(384)`, not null | paraphrase-multilingual-MiniLM-L12-v2 (см. ADR-0011) |
| `meta` | jsonb | доп. атрибуты |

Индексы: HNSW/IVFFlat по `embedding` (cosine); `(document_id)`.

## Соглашения

- Все таблицы имеют суррогатный `bigint` PK, кроме справочников с текстовым
  кодом (`scenarios`, `mistake_catalog`).
- Времена — `timestamptz`, в UTC.
- Гибкие/варьирующиеся поля — `jsonb`.
- Удаление пользовательских данных (`/delete`) — soft-delete + каскадная очистка
  сессий и сообщений в рамках задачи.
- Схема эволюционирует **только через Alembic-миграции**.
