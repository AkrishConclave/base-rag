# RAG Pinbox - Система поддержки на основе RAG

RAG-система для ответов на вопросы пользователей на основе базы знаний статей поддержки Pinbox.

[![CI](https://github.com/AkrishConclave/rag-pinbox/actions/workflows/ci.yml/badge.svg)](https://github.com/AkrishConclave/rag-pinbox/actions/workflows/ci.yml)

> 📖 **Подробная документация по архитектуре:** см. [ARCHITECTURE.md](./ARCHITECTURE.md)

## Структура проекта

```
rag-pinbox/
├── api/                    # Python API сервер
│   ├── ingest.py          # Индексация статей в ChromaDB
│   ├── query.py           # Поиск и генерация ответов
│   ├── server.py          # FastAPI сервер
│   ├── requirements.txt   # Python зависимости
│   └── .env              # Переменные окружения (создать самостоятельно)
├── docker/                # Docker конфигурация
│   ├── docker-compose.yml
│   └── Dockerfile.api
├── php/                   # PHP клиент
│   └── ask.php
└── support_*.json        # JSON файл со статьями поддержки
```

> 💡 Для детального описания структуры проекта, компонентов и архитектуры см. [ARCHITECTURE.md](./ARCHITECTURE.md)

## Требования

- Docker и Docker Compose
- API ключ от OpenRouter (https://openrouter.ai/)

## Настройка

### 1. Создайте файл `.env` в папке `api/`

```env
# OpenRouter API Key (обязательно!)
OPENROUTER_API_KEY=sk-or-v1-ваш_ключ_здесь

# Модель через OpenRouter (опционально, по умолчанию deepseek/deepseek-chat)
# Можно использовать любую модель: openai/gpt-4, anthropic/claude-3-opus, google/gemini-pro и т.д.
OPENROUTER_MODEL=deepseek/deepseek-chat

# ChromaDB директория (опционально, по умолчанию ./chroma_db)
CHROMA_DIR=./chroma_db

# Модель для эмбеддингов (опционально)
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Количество релевантных документов (опционально)
TOP_K=5
```

### 2. Убедитесь, что JSON файл находится в корне проекта

Файл должен начинаться с `support_` и иметь расширение `.json`, например:
- `support_202511221211.json`

## Запуск

### Запуск через Docker Compose (Development)

```bash
cd docker
docker-compose up -d
```

Сервисы будут доступны:
- **API сервер**: http://localhost:9001
- **ChromaDB**: http://localhost:8001

### Запуск в Production

```bash
cd docker
# Запуск контейнеров
docker-compose -f docker-compose.prod.yml up -d

# Остановка контейнеров
docker-compose -f docker-compose.prod.yml down

# Перезапуск только API сервера
docker-compose -f docker-compose.prod.yml restart rag_api

# Просмотр логов API
docker-compose -f docker-compose.prod.yml logs -f rag_api

# Остановка всех сервисов
docker-compose -f docker-compose.prod.yml stop

# Запуск остановленных сервисов
docker-compose -f docker-compose.prod.yml start
```

> 💡 **Примечание:** Для продакшена используется файл `docker-compose.prod.yml` и переменные окружения из `deployment/prod.env`

### Первый запуск

1. **Индексация данных** (обязательно перед использованием):
   ```bash
   curl -X POST http://localhost:9001/ingest
   ```
   
   Или через браузер: http://localhost:9001/ingest

2. **Проверка работы**:
   ```bash
   curl -X POST http://localhost:9001/ask \
     -H "Content-Type: application/json" \
     -d '{"q": "Как настроить оповещения?"}'
   ```

## API Endpoints

### POST `/ingest`
Индексирует статьи из JSON файла в векторную базу данных.

**Ответ:**
```json
{
  "indexed_chunks": 1234
}
```

### POST `/ask`
Отвечает на вопрос пользователя на основе проиндексированных статей.

**Запрос (публичный режим - только status=1):**
```json
{
  "q": "Как настроить оповещения?"
}
```

**Запрос (админ режим - все статьи, включая status=0):**
```json
{
  "q": "отзывы",
  "admin_mode": true
}
```

**Параметры:**
- `q` (обязательно) - вопрос пользователя
- `use_hybrid` (опционально, по умолчанию `false`) - использовать гибридный поиск (BM25 + векторный)
- `admin_mode` (опционально, по умолчанию `false`) - если `true`, показывает все статьи (status=0 и status=1), иначе только публичные (status=1)

**Ответ:**
```json
{
  "answer": "Для настройки оповещений...",
  "sources": [
    {
      "title": "Оповещение Email",
      "id": "2",
      "dist": 0.1234
    }
  ]
}
```

**Важно:** Статьи с `status=0` (для staff) не показываются в обычном режиме. Используйте `admin_mode: true` для доступа к ним.

### DELETE `/api/debug/clear-index`
Очищает все данные из ChromaDB индекса (удаляет коллекцию).

**Ответ:**
```json
{
  "success": true,
  "message": "Индекс успешно очищен",
  "deleted_count": 313
}
```

### DELETE `/api/debug/clear-cache`
Очищает весь кэш запросов LLM.

**Ответ:**
```json
{
  "success": true,
  "message": "Кэш успешно очищен",
  "cache_type": "sqlite"
}
```

### POST `/api/debug/test-llm`
Проверяет соединение с LLM для расширения поисковых запросов.

**Запрос:**
```json
{
  "query": "как настроить оповещения"
}
```

**Ответ:**
```json
{
  "success": true,
  "query": "как настроить оповещения",
  "expanded_query": "оповещения уведомления email telegram настройка",
  "provider": "openrouter",
  "model": "deepseek/deepseek-chat",
  "response_time_ms": 1234.56
}
```

## Локальный запуск (без Docker)

### Установка зависимостей

```bash
cd api
pip install -r requirements.txt
```

### Запуск сервера

```bash
python server.py
```

### Индексация данных

```bash
python -m ingest
```

Или через API:
```bash
curl -X POST http://localhost:9001/ingest
```

## Тестирование с Postman

В проекте есть готовая коллекция Postman для тестирования API (v2.0):

1. **Импортируйте коллекцию**:
   - Откройте Postman
   - Нажмите Import
   - Выберите файл `Postman_Collection.json`

2. **Импортируйте окружение** (опционально):
   - Импортируйте `Postman_Environment.json` для переменных окружения
   - Или создайте переменную `base_url` со значением `http://localhost:9001`

3. **Структура коллекции**:
   - **Health & Status** - Health Check endpoint
   - **Ingest** - индексация данных (выполните первым)
   - **RAG - Поиск и ответы** - запросы с вопросами:
     - Векторный поиск (по умолчанию)
     - Гибридный поиск (с `use_hybrid: true`)
     - Примеры вопросов
   - **Embed** - создание эмбеддингов
   - **Debug** - отладочные endpoints

4. **Новые возможности v2.0**:
   - ✅ Гибридный поиск (BM25 + векторный)
   - ✅ Health Check для мониторинга
   - ✅ Debug endpoints для отладки
   - ✅ Создание эмбеддингов
   - ✅ Кэширование ответов (автоматически)

> 📖 **Подробное руководство:** см. [POSTMAN_GUIDE.md](./POSTMAN_GUIDE.md)

## Использование PHP клиента

```php
<?php
$q = "Как настроить оповещения?";
$ch = curl_init("http://127.0.0.1:9001/ask");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_HTTPHEADER => ["Content-Type: application/json"],
    CURLOPT_POSTFIELDS => json_encode(["q" => $q]),
]);
$res = curl_exec($ch);
$data = json_decode($res, true);
echo $data["answer"];
?>
```

## Устранение неполадок

### Ошибка "Коллекция не найдена"
Выполните индексацию через `/ingest` endpoint.

### Ошибка "OPENROUTER_API_KEY не установлен"
Проверьте, что файл `.env` создан и содержит правильный API ключ OpenRouter.

### Ошибка при чтении JSON файла
Убедитесь, что файл `support_*.json` находится в корне проекта и имеет правильный формат.

## CI/CD

Проект использует минимальный CI через GitHub Actions:

- **CI** - автоматический линтинг кода при каждом PR (только проверка критических ошибок синтаксиса)

> ⚠️ **Примечание:** Docker сборки отключены для экономии места на диске в GitHub Actions.

## Технологии

- **FastAPI** - веб-фреймворк
- **ChromaDB** - векторная база данных
- **Sentence Transformers** - создание эмбеддингов
- **OpenRouter API** - генерация ответов (с автоматическим fallback на резервные модели)
- **Docker** - контейнеризация
- **GitHub Actions** - CI/CD

