#!/bin/bash
# Скрипт деплоя RAG Pinbox на продакшн сервер
# Использование: bash deployment/deploy.sh
# Запускать от пользователя deploy (или с sudo -u deploy)

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
PROJECT_DIR="/opt/rag-pinbox"
DOCKER_DIR="$PROJECT_DIR/docker"
ENV_FILE="$PROJECT_DIR/deployment/prod.env"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.prod.yml"

# Функция для вывода сообщений
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Проверка, что скрипт запущен из правильной директории
if [ ! -d "$PROJECT_DIR" ]; then
    log_error "Директория проекта не найдена: $PROJECT_DIR"
    log_info "Убедитесь, что проект клонирован в /opt/rag-pinbox"
    exit 1
fi

cd "$PROJECT_DIR"

# Проверка наличия необходимых команд
log_info "Проверка необходимых инструментов..."

if ! command -v git &> /dev/null; then
    log_error "Git не установлен"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    log_error "Docker не установлен"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "Docker Compose не установлен"
    exit 1
fi

log_success "Все необходимые инструменты установлены"

# Проверка файла окружения
log_info "Проверка файла окружения..."
if [ ! -f "$ENV_FILE" ]; then
    log_warning "Файл $ENV_FILE не найден"
    log_info "Создаю файл из примера..."
    if [ -f "$PROJECT_DIR/deployment/prod.env.example" ]; then
        cp "$PROJECT_DIR/deployment/prod.env.example" "$ENV_FILE"
        log_warning "⚠️  ВАЖНО: Отредактируйте $ENV_FILE и заполните все необходимые переменные!"
        log_warning "Особенно важно установить OPENROUTER_API_KEY"
        read -p "Нажмите Enter после редактирования файла или Ctrl+C для отмены..."
    else
        log_error "Файл примера не найден: $PROJECT_DIR/deployment/prod.env.example"
        exit 1
    fi
fi

# Проверка обязательных переменных в .env файле
log_info "Проверка обязательных переменных окружения..."
REQUIRED_VARS=("OPENROUTER_API_KEY")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" "$ENV_FILE" || grep -q "^${var}=$" "$ENV_FILE" || grep -q "^${var}=.*your.*key" "$ENV_FILE"; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    log_error "Обнаружены незаполненные обязательные переменные:"
    for var in "${MISSING_VARS[@]}"; do
        log_error "  - $var"
    done
    log_info "Отредактируйте файл: $ENV_FILE"
    exit 1
fi

log_success "Все обязательные переменные настроены"

# Вывод переменных окружения для диагностики
log_info "Проверка переменных окружения из $ENV_FILE..."
echo ""
log_info "════════════════════════════════════════════════════════"
log_info "Переменные окружения:"
log_info "════════════════════════════════════════════════════════"

# Группировка переменных по категориям
log_info "OpenRouter настройки:"
grep "^OPENROUTER" "$ENV_FILE" 2>/dev/null | while IFS='=' read -r key value; do
    if [ "$key" = "OPENROUTER_API_KEY" ]; then
        # Маскируем API ключ
        if [ ${#value} -gt 14 ]; then
            masked_value="${value:0:10}...${value: -4}"
        else
            masked_value="***masked***"
        fi
        log_info "  $key=$masked_value"
    else
        log_info "  $key=$value"
    fi
done || log_info "  (не найдено)"

log_info ""
log_info "ChromaDB настройки:"
grep "^CHROMA" "$ENV_FILE" 2>/dev/null | sed 's/^/  /' || log_info "  (не найдено)"

log_info ""
log_info "Другие настройки:"
grep -v "^#" "$ENV_FILE" 2>/dev/null | grep -v "^OPENROUTER" | grep -v "^CHROMA" | grep -v "^$" | sed 's/^/  /' || log_info "  (не найдено)"

echo ""
log_success "Переменные окружения загружены"

# Проверка docker-compose файла
if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "Файл docker-compose не найден: $COMPOSE_FILE"
    exit 1
fi

# Проверка доступа к Docker
log_info "Проверка доступа к Docker..."
if ! docker ps &> /dev/null; then
    log_error "Нет доступа к Docker. Убедитесь, что пользователь в группе docker"
    log_info "Выполните: sudo usermod -aG docker $USER"
    exit 1
fi

log_success "Доступ к Docker подтвержден"

# Обновление кода из репозитория
log_info "Обновление кода из Git..."
if [ -d "$PROJECT_DIR/.git" ]; then
    # Сохраняем текущую ветку
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    
    log_info "Текущая ветка: $CURRENT_BRANCH"
    log_info "Получение изменений из репозитория..."
    
    git fetch origin || {
        log_warning "Не удалось получить изменения из Git. Продолжаю с текущей версией..."
    }
    
    # Проверяем, есть ли изменения
    if git diff --quiet HEAD origin/$CURRENT_BRANCH 2>/dev/null; then
        log_success "Код уже актуален"
    else
        log_info "Обнаружены новые изменения. Обновляю код..."
        git reset --hard origin/$CURRENT_BRANCH || {
            log_error "Не удалось обновить код из Git"
            exit 1
        }
        log_success "Код обновлен"
    fi
else
    log_warning "Директория не является Git репозиторием. Пропускаю обновление кода."
fi

# Переход в директорию docker
cd "$DOCKER_DIR"

# Остановка старых контейнеров (если запущены)
log_info "Остановка старых контейнеров (если запущены)..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Очистка Docker (опционально, через CLEAN_DOCKER=true)
if [ "${CLEAN_DOCKER:-false}" = "true" ]; then
    log_info "Очистка Docker кэша и неиспользуемых ресурсов (CLEAN_DOCKER=true)..."
    log_info "Очистка неиспользуемых образов..."
    docker image prune -a -f 2>/dev/null || true
    
    log_info "Очистка неиспользуемых volumes..."
    docker volume prune -f 2>/dev/null || true
    
    log_info "Очистка build кэша..."
    docker builder prune -a -f 2>/dev/null || true
    
    log_info "Очистка неиспользуемых сетей..."
    docker network prune -f 2>/dev/null || true
    
    log_success "Очистка завершена"
else
    log_info "Очистка Docker пропущена (для очистки установите CLEAN_DOCKER=true)"
fi

# Показываем использование Docker
log_info "Текущее использование Docker:"
docker system df

# Пересборка образов (БЕЗ --no-cache для экономии памяти)
log_info "Пересборка Docker образов (с использованием кэша)..."
if docker-compose -f docker-compose.prod.yml build; then
    log_success "Образы успешно собраны"
else
    log_error "Ошибка при сборке образов"
    exit 1
fi

# Запуск контейнеров
log_info "Запуск контейнеров..."
if docker-compose -f docker-compose.prod.yml up -d; then
    log_success "Контейнеры запущены"
else
    log_error "Ошибка при запуске контейнеров"
    exit 1
fi

# Ожидание запуска сервисов
log_info "Ожидание запуска сервисов (30 секунд для загрузки моделей)..."
sleep 30

# Переменные для хранения результатов проверок
FAILED_CONTAINERS=()
API_HEALTH_OK=false
API_ENDPOINTS_OK=false
CHROMA_OK=false
REDIS_OK=false
CRITICAL_ERRORS=""

# Проверка статуса контейнеров
log_info "Проверка статуса контейнеров..."
echo ""
docker-compose -f docker-compose.prod.yml ps
echo ""

# Проверка здоровья контейнеров
log_info "Проверка здоровья контейнеров..."
for container in rag_api chroma rag-redis; do
    if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "unknown")
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")
        
        if [ "$STATUS" = "running" ]; then
            if [ "$HEALTH" = "healthy" ] || [ "$HEALTH" = "none" ]; then
                log_success "Контейнер $container: запущен (health: $HEALTH)"
            else
                log_warning "Контейнер $container: запущен, но health: $HEALTH"
            fi
        else
            log_error "Контейнер $container: статус $STATUS"
            FAILED_CONTAINERS+=("$container")
        fi
    else
        log_error "Контейнер $container: не найден"
        FAILED_CONTAINERS+=("$container")
    fi
done

# Проверка логов API на критические ошибки
log_info "Проверка логов API на критические ошибки..."
API_ERRORS=$(docker-compose -f docker-compose.prod.yml logs rag_api 2>&1 | grep -i "error\|exception\|traceback\|fatal" | tail -10 || true)

if [ -n "$API_ERRORS" ]; then
    log_warning "Обнаружены ошибки в логах API:"
    echo "$API_ERRORS"
    echo ""
    CRITICAL_ERRORS="$CRITICAL_ERRORS\nAPI Errors: $API_ERRORS"
else
    log_success "Критических ошибок в логах API не обнаружено"
fi

# Показываем последние строки логов API для диагностики
log_info "Последние строки логов API:"
docker-compose -f docker-compose.prod.yml logs rag_api --tail=20 2>&1 | tail -10
echo ""

# Детальная проверка работоспособности API
log_info "Детальная проверка работоспособности API..."

# Проверка 1: Health endpoint с повторными попытками
log_info "Проверка /health endpoint (с повторными попытками)..."
MAX_RETRIES=5
RETRY_DELAY=5
HEALTH_CODE="000"
HEALTH_BODY=""

for i in $(seq 1 $MAX_RETRIES); do
    log_info "Попытка $i из $MAX_RETRIES..."
    HEALTH_RESPONSE=$(curl -f -s -w "\n%{http_code}" --max-time 5 http://localhost:9001/health 2>&1 || echo "FAILED")
    HEALTH_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
    HEALTH_BODY=$(echo "$HEALTH_RESPONSE" | head -n -1)
    
    if [ "$HEALTH_CODE" = "200" ]; then
        log_success "✓ /health endpoint отвечает (HTTP $HEALTH_CODE)"
        API_HEALTH_OK=true
        if echo "$HEALTH_BODY" | grep -q "ok\|status\|healthy"; then
            log_success "  Ответ: $HEALTH_BODY"
        fi
        break
    else
        if [ $i -lt $MAX_RETRIES ]; then
            log_warning "  Не удалось подключиться, жду ${RETRY_DELAY} секунд..."
            sleep $RETRY_DELAY
        else
            log_error "✗ /health endpoint не отвечает после $MAX_RETRIES попыток"
            log_error "  Последний ответ: $HEALTH_RESPONSE"
            CRITICAL_ERRORS="$CRITICAL_ERRORS\nHealth endpoint failed after $MAX_RETRIES attempts: $HEALTH_RESPONSE"
        fi
    fi
done

# Проверка 2: Root endpoint (если есть)
log_info "Проверка корневого endpoint..."
ROOT_RESPONSE=$(curl -f -s -w "\n%{http_code}" http://localhost:9001/ 2>&1 || echo "FAILED")
ROOT_CODE=$(echo "$ROOT_RESPONSE" | tail -1)

if [ "$ROOT_CODE" = "200" ] || [ "$ROOT_CODE" = "404" ]; then
    log_success "✓ Корневой endpoint доступен (HTTP $ROOT_CODE)"
    API_ENDPOINTS_OK=true
else
    log_warning "⚠ Корневой endpoint: HTTP $ROOT_CODE"
fi

# Проверка 3: Проверка ChromaDB через API (если есть endpoint для проверки)
log_info "Проверка подключения к ChromaDB..."
CHROMA_LOGS=$(docker-compose -f docker-compose.prod.yml logs chroma 2>&1 | tail -5 || true)
if echo "$CHROMA_LOGS" | grep -qi "error\|fatal\|exception"; then
    log_warning "⚠ Обнаружены проблемы в логах ChromaDB"
    CRITICAL_ERRORS="$CRITICAL_ERRORS\nChromaDB issues: $CHROMA_LOGS"
else
    log_success "✓ ChromaDB работает нормально"
    CHROMA_OK=true
fi

# Проверка 4: Проверка Redis
log_info "Проверка подключения к Redis..."
if docker exec rag-redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    log_success "✓ Redis отвечает на ping"
    REDIS_OK=true
else
    log_warning "⚠ Redis не отвечает на ping"
    CRITICAL_ERRORS="$CRITICAL_ERRORS\nRedis ping failed"
fi

# Проверка 5: Проверка доступности портов
log_info "Проверка доступности портов..."
if netstat -tln 2>/dev/null | grep -q ":9001" || ss -tln 2>/dev/null | grep -q ":9001"; then
    log_success "✓ Порт 9001 (API) слушается"
else
    log_error "✗ Порт 9001 (API) не слушается"
    CRITICAL_ERRORS="$CRITICAL_ERRORS\nPort 9001 not listening"
fi

if netstat -tln 2>/dev/null | grep -q ":8001" || ss -tln 2>/dev/null | grep -q ":8001"; then
    log_success "✓ Порт 8001 (ChromaDB) слушается"
else
    log_warning "⚠ Порт 8001 (ChromaDB) не слушается"
fi

# Итоговая оценка работоспособности
echo ""
log_info "════════════════════════════════════════════════════════"
log_info "Итоговая оценка работоспособности:"
log_info "════════════════════════════════════════════════════════"

APPLICATION_WORKING=true

if [ ${#FAILED_CONTAINERS[@]} -gt 0 ]; then
    log_error "✗ Некоторые контейнеры не запущены"
    APPLICATION_WORKING=false
else
    log_success "✓ Все контейнеры запущены"
fi

if [ "$API_HEALTH_OK" = true ]; then
    log_success "✓ API Health endpoint работает"
else
    log_error "✗ API Health endpoint не работает"
    APPLICATION_WORKING=false
fi

if [ "$CHROMA_OK" = true ]; then
    log_success "✓ ChromaDB работает"
else
    log_warning "⚠ ChromaDB может иметь проблемы"
fi

if [ "$REDIS_OK" = true ]; then
    log_success "✓ Redis работает"
else
    log_warning "⚠ Redis может иметь проблемы"
fi

if [ -n "$CRITICAL_ERRORS" ]; then
    log_error "✗ Обнаружены критические ошибки"
    APPLICATION_WORKING=false
fi

# Итоговый отчет и действия на основе проверок
echo ""
log_success "════════════════════════════════════════════════════════"
if [ "$APPLICATION_WORKING" = true ]; then
    log_success "✅ ДЕПЛОЙ УСПЕШЕН - Приложение работает!"
    log_success "════════════════════════════════════════════════════════"
    echo ""
    log_info "Полезные команды:"
    log_info "  Просмотр логов: docker-compose -f docker-compose.prod.yml logs -f"
    log_info "  Статус: docker-compose -f docker-compose.prod.yml ps"
    log_info "  Остановка: docker-compose -f docker-compose.prod.yml down"
    log_info "  Перезапуск: docker-compose -f docker-compose.prod.yml restart"
    echo ""
    log_success "🎉 Проект успешно развернут и работает!"
    exit 0
else
    log_error "❌ ДЕПЛОЙ ЗАВЕРШЕН С ОШИБКАМИ"
    log_success "════════════════════════════════════════════════════════"
    echo ""
    
    # Детальная информация об ошибках
    if [ ${#FAILED_CONTAINERS[@]} -gt 0 ]; then
        log_error "Не запущенные контейнеры:"
        for container in "${FAILED_CONTAINERS[@]}"; do
            log_error "  - $container"
            log_info "    Логи: docker-compose -f docker-compose.prod.yml logs $container"
        done
        echo ""
    fi
    
    if [ -n "$CRITICAL_ERRORS" ]; then
        log_error "Критические ошибки:"
        echo -e "$CRITICAL_ERRORS"
        echo ""
    fi
    
    # Предложения по исправлению
    log_info "Рекомендации по исправлению:"
    log_info "1. Проверьте логи проблемных контейнеров:"
    log_info "   docker-compose -f docker-compose.prod.yml logs -f rag_api"
    log_info "   docker-compose -f docker-compose.prod.yml logs -f chroma"
    log_info ""
    log_info "2. Проверьте файл окружения: $ENV_FILE"
    log_info ""
    log_info "3. Попробуйте перезапустить контейнеры:"
    log_info "   docker-compose -f docker-compose.prod.yml restart"
    log_info ""
    log_info "4. Если проблема сохраняется, проверьте системные ресурсы:"
    log_info "   docker stats"
    log_info "   df -h"
    log_info "   free -h"
    echo ""
    
    exit 1
fi

