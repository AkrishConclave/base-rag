# CI/CD Configuration

## GitHub Actions Workflows

### 1. CI - Tests and Linting (`ci.yml`)

**Триггеры:** Push и Pull Request в `main` и `develop`

**Jobs:**
- **lint** - Проверка кода с flake8 и black
- **test** - Запуск тестов с ChromaDB сервисом
- **docker-build** - Сборка Docker образа для проверки

### 2. CD - Build and Deploy (`cd.yml`)

**Триггеры:** Push в `main`, теги `v*`, manual dispatch

**Jobs:**
- **build-and-push** - Сборка и публикация Docker образа в GitHub Container Registry
- **deploy-staging** - Деплой в staging (при push в main)
- **deploy-production** - Деплой в production (при создании тега)

### 3. Test API Endpoints (`test-api.yml`)

**Триггеры:** Push, PR, manual dispatch

**Проверяет:**
- Health check endpoint
- Swagger UI доступность
- Структуру приложения

### 4. Docker Build (`docker-build.yml`)

**Триггеры:** Изменения в `api/` или `docker/`

**Проверяет:**
- Корректность сборки Docker образа
- Работоспособность образа

### 5. Release (`release.yml`)

**Триггеры:** Теги вида `v*.*.*`

**Создает:**
- GitHub Release с автоматическим changelog

## Dependabot

Автоматическое обновление зависимостей:
- Python пакеты (еженедельно)
- Docker образы (еженедельно)
- GitHub Actions (еженедельно)

## Templates

- **Pull Request Template** - Шаблон для PR
- **Issue Templates** - Шаблоны для bug reports и feature requests

## Настройка Secrets

Для работы CI/CD необходимо настроить в GitHub Settings → Secrets:

- `OPENROUTER_API_KEY` - для тестирования (опционально)
- Другие секреты для деплоя (если используются)

## Использование

### Автоматический запуск

Workflows запускаются автоматически при:
- Push в `main` или `develop`
- Создании Pull Request
- Создании тега `v*.*.*`

### Ручной запуск

Некоторые workflows можно запустить вручную через GitHub Actions UI:
- `Test API Endpoints` - через workflow_dispatch
- `CD - Build and Deploy` - через workflow_dispatch

### Создание релиза

```bash
git tag v1.0.0
git push origin v1.0.0
```

Автоматически создастся GitHub Release с changelog.

