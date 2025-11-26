# RAG Pinbox - Система поддержки на основе RAG

RAG-система для ответов на вопросы пользователей на основе базы знаний статей поддержки Pinbox.

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

### Запуск через Docker Compose

```bash
cd docker
docker-compose up -d
```

Сервисы будут доступны:
- **API сервер**: http://localhost:9001
- **ChromaDB**: http://localhost:8001

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

**Запрос:**
```json
{
  "q": "Как настроить оповещения?"
}
```

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

## Технологии

- **FastAPI** - веб-фреймворк
- **ChromaDB** - векторная база данных
- **Sentence Transformers** - создание эмбеддингов
- **OpenRouter API** - генерация ответов (с автоматическим fallback на резервные модели)
- **Docker** - контейнеризация

