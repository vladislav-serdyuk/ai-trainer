#!/usr/bin/env bash
set -e

# Прямой запуск произвольной команды (например, tools/bot_cli.py для E2E):
# docker compose run --rm --no-deps -T bot python tools/bot_cli.py
if [ $# -gt 0 ]; then
  exec "$@"
fi

# Ждём БД (на случай если healthcheck немного запаздывает)
python -c "
import asyncio, sys
from ai_trainer.repository.session import get_session_factory, get_engine
async def main():
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            pass
        await engine.dispose()
        print('DB OK')
    except Exception as e:
        print(f'DB ERR: {e}', file=sys.stderr)
        sys.exit(1)
asyncio.run(main())
"

# Применяем миграции
alembic upgrade head

# Заполняем сид-данные (идемпотентно внутри seed.py при наличии)
python -m ai_trainer.repository.seed || true

# Инициализируем базу знаний
python -m ai_trainer.rag.ingest || true

# Прогреваем модели RAG (embedding + реранкер): скачиваем и грузим до старта
# бота, чтобы первый запрос пользователя не ждал загрузку моделей.
# При выключенном реранке (RERANKER_MODEL не задан) шаг безвреден.
python -c "
from ai_trainer.rag.embeddings import get_embedder
from ai_trainer.rag.rerank import get_reranker
get_embedder().embed_query('прогрев')
get_reranker().rerank('прогрев', ['прогрев модели реранкера'])
print('RAG models OK')
" || true

# Прогреваем STT-модель: скачиваем её с HuggingFace до старта, чтобы первый
# голосовой не ждал загрузку (а кэш лежит на volume и переживает пересоздание
# контейнера). Загрузка с HF может флакить — несколько попыток.
for i in 1 2 3; do
  python -c "
from ai_trainer.config import get_settings
from ai_trainer.stt.transcribe import FasterWhisperTranscriber
FasterWhisperTranscriber(get_settings())._get_model()
print('STT model OK')
" && break
  echo "STT warmup attempt $i failed, retrying..." >&2
  sleep 5
done || true

exec python -m ai_trainer.bot.main
