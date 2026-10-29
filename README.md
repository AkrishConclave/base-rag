# RAG Support API

Сервис поиска и генерации ответов по локальной базе знаний. Статьи
индексируются в ChromaDB; ответы формируются через настроенного LLM-провайдера.

## Требования

- Docker и Docker Compose, либо Python 3.12;
- API-ключ и идентификатор каталога Yandex AI Studio для генерации ответов;
- локальный экспорт базы знаний `support_*.json`. Такие файлы намеренно не
  отслеживаются Git.

## Настройка

Скопируйте [api/.env.example](api/.env.example) в `api/.env` и заполните
`YANDEX_CLOUD_FOLDER` и `YANDEX_CLOUD_API_KEY`:

```env
YANDEX_CLOUD_FOLDER=your-folder-id
YANDEX_CLOUD_API_KEY=your-api-key
YANDEX_CLOUD_MODEL=deepseek-v4-flash/latest
YANDEX_CLOUD_BASE_URL=https://ai.api.cloud.yandex.net/v1
YANDEX_CLOUD_TEMPERATURE=0.3
YANDEX_CLOUD_MAX_OUTPUT_TOKENS=65536
CHROMA_DIR=./chroma_db
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
TOP_K=5
ADMIN_TOKEN=replace-with-a-long-random-value
JWT_SECRET=replace-with-a-long-random-value
```

Файл [support_example.json](support_example.json) показывает ожидаемую
структуру. Положите настоящий экспорт в корень проекта под именем
`support_*.json`, например `support_202511221211.json`. Экспорт останется
только на вашей машине: он игнорируется Git и пример не выбирается для
индексации.

## Запуск

```bash
cd docker
docker compose up -d
```

API доступен на `http://localhost:9001`, ChromaDB — на
`http://localhost:8001`.

## Основные запросы

Все служебные маршруты требуют заголовок `X-Admin-Token`.

```bash
# Индексация базы знаний
curl -X POST http://localhost:9001/api/ingest \
  -H 'X-Admin-Token: replace-with-a-long-random-value'

# Публичный поиск
curl -X POST http://localhost:9001/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"q":"Как настроить уведомления?"}'

# Проверка состояния
curl http://localhost:9001/health
```

Доступны также защищённые маршруты загрузки и скачивания `support_*.json`:
`POST /api/upload-support` и `GET /api/download-support`.

## Тесты

```bash
python -m pip install -r api/requirements.txt pytest
PYTHONPATH=. pytest api/tests -q
```

Совместимые маршруты без префикса `/api` не поддерживаются.

## Лицензия

MIT. При копировании или существенном использовании кода необходимо сохранять
уведомление об авторских правах: `Copyright (c) 2026 AkrishConclave`.
