#!/bin/bash
# Скрипт подготовки VPS Ubuntu 24.04 для деплоя RAG Support
# Использование: sudo bash setup-server.sh

set -e

echo "🚀 Начинаем подготовку сервера для RAG Support..."

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка, что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Пожалуйста, запустите скрипт с sudo${NC}"
    exit 1
fi

# Обновление системы
echo -e "${GREEN}📦 Обновление системы...${NC}"
apt-get update
apt-get upgrade -y

# Установка базовых утилит
echo -e "${GREEN}📦 Установка базовых утилит...${NC}"
apt-get install -y \
    curl \
    wget \
    git \
    vim \
    nano \
    htop \
    ufw \
    fail2ban \
    unattended-upgrades

# Установка Docker
echo -e "${GREEN}🐳 Установка Docker...${NC}"
if ! command -v docker &> /dev/null; then
    # Удаляем старые версии
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    
    # Устанавливаем зависимости
    apt-get install -y \
        ca-certificates \
        gnupg \
        lsb-release
    
    # Добавляем официальный GPG ключ Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Добавляем репозиторий Docker
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Устанавливаем Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    echo -e "${GREEN}✅ Docker установлен${NC}"
else
    echo -e "${YELLOW}⚠️  Docker уже установлен${NC}"
fi

# Установка Docker Compose (standalone, если не установлен через plugin)
if ! command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}📦 Установка Docker Compose (standalone)...${NC}"
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✅ Docker Compose установлен${NC}"
else
    echo -e "${YELLOW}⚠️  Docker Compose уже установлен${NC}"
fi

# Создание пользователя для деплоя (если не существует)
DEPLOY_USER="deploy"
if ! id "$DEPLOY_USER" &>/dev/null; then
    echo -e "${GREEN}👤 Создание пользователя $DEPLOY_USER...${NC}"
    useradd -m -s /bin/bash $DEPLOY_USER
    usermod -aG docker $DEPLOY_USER
    usermod -aG sudo $DEPLOY_USER
    echo -e "${GREEN}✅ Пользователь $DEPLOY_USER создан${NC}"
else
    echo -e "${YELLOW}⚠️  Пользователь $DEPLOY_USER уже существует${NC}"
    usermod -aG docker $DEPLOY_USER 2>/dev/null || true
fi

# Создание директории для проекта
PROJECT_DIR="/opt/rag-support"
echo -e "${GREEN}📁 Проверка директории проекта...${NC}"
if [ ! -d "$PROJECT_DIR" ]; then
    mkdir -p $PROJECT_DIR
    chown $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR
    echo -e "${GREEN}✅ Директория проекта создана${NC}"
else
    echo -e "${YELLOW}⚠️  Директория проекта уже существует${NC}"
    # Устанавливаем правильные права, если репозиторий уже клонирован
    chown -R $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR 2>/dev/null || true
fi

# Создание директории для данных (если не существует)
echo -e "${GREEN}📁 Создание директорий для данных...${NC}"
mkdir -p $PROJECT_DIR/chroma_db
mkdir -p $PROJECT_DIR/logs
chown -R $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR/chroma_db $PROJECT_DIR/logs 2>/dev/null || true

# Настройка SSH для деплоя
echo -e "${GREEN}🔐 Настройка SSH...${NC}"
SSH_DIR="/home/$DEPLOY_USER/.ssh"
mkdir -p $SSH_DIR
chmod 700 $SSH_DIR
chown -R $DEPLOY_USER:$DEPLOY_USER $SSH_DIR

# Создание authorized_keys если не существует
if [ ! -f "$SSH_DIR/authorized_keys" ]; then
    touch $SSH_DIR/authorized_keys
    chmod 600 $SSH_DIR/authorized_keys
    chown $DEPLOY_USER:$DEPLOY_USER $SSH_DIR/authorized_keys
fi

# Настройка firewall
echo -e "${GREEN}🔥 Настройка firewall...${NC}"
ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw allow 9001/tcp # API (если нужно открыть напрямую)
echo -e "${GREEN}✅ Firewall настроен${NC}"

# Настройка fail2ban
echo -e "${GREEN}🛡️  Настройка fail2ban...${NC}"
systemctl enable fail2ban
systemctl start fail2ban
echo -e "${GREEN}✅ Fail2ban настроен${NC}"

# Настройка автоматических обновлений безопасности
echo -e "${GREEN}🔄 Настройка автоматических обновлений...${NC}"
cat > /etc/apt/apt.conf.d/50unattended-upgrades <<EOF
Unattended-Upgrade::Allowed-Origins {
    "\${distro_id}:\${distro_codename}-security";
    "\${distro_id}:\${distro_codename}-updates";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
echo -e "${GREEN}✅ Автоматические обновления настроены${NC}"

# Создание скрипта для деплоя
echo -e "${GREEN}📝 Создание скрипта деплоя...${NC}"
cat > /usr/local/bin/deploy-rag-support <<'DEPLOY_SCRIPT'
#!/bin/bash
# Скрипт для деплоя RAG Support
# Использование: sudo deploy-rag-support

set -e

PROJECT_DIR="/opt/rag-support"
DEPLOY_USER="deploy"

cd $PROJECT_DIR

echo "🔄 Обновление кода из Git..."
sudo -u $DEPLOY_USER git fetch origin
sudo -u $DEPLOY_USER git reset --hard origin/main

echo "🐳 Пересборка и перезапуск контейнеров..."
cd docker
sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml pull
sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml up -d --build

echo "✅ Деплой завершен!"
echo "📊 Статус контейнеров:"
sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml ps
DEPLOY_SCRIPT

chmod +x /usr/local/bin/deploy-rag-support
echo -e "${GREEN}✅ Скрипт деплоя создан${NC}"

# Создание инструкции для настройки SSH ключа
echo -e "${GREEN}📋 Создание инструкции...${NC}"
cat > $PROJECT_DIR/DEPLOY_SETUP.md <<EOF
# Инструкция по настройке деплоя

## 1. Добавление SSH ключа для деплоя

На вашем локальном компьютере выполните:

\`\`\`bash
# Генерируем SSH ключ (если еще нет)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/rag-support_deploy

# Копируем публичный ключ на сервер
ssh-copy-id -i ~/.ssh/rag-support_deploy.pub $DEPLOY_USER@$(hostname -I | awk '{print $1}')
\`\`\`

Или вручную:

\`\`\`bash
# Показываем публичный ключ
cat ~/.ssh/rag-support_deploy.pub

# На сервере добавляем его в authorized_keys
# sudo -u $DEPLOY_USER nano /home/$DEPLOY_USER/.ssh/authorized_keys
# Вставьте содержимое публичного ключа
\`\`\`

## 2. Настройка GitHub Secrets

В GitHub репозитории перейдите в Settings → Secrets and variables → Actions и добавьте:

- \`DEPLOY_HOST\`: IP адрес или домен сервера
- \`DEPLOY_USER\`: $DEPLOY_USER
- \`DEPLOY_SSH_KEY\`: Содержимое приватного ключа (~/.ssh/rag-support_deploy)
- \`DEPLOY_PORT\`: 22 (или другой порт SSH)
- \`DEPLOY_PATH\`: $PROJECT_DIR

## 3. Настройка переменных окружения

Если репозиторий еще не клонирован, выполните:
\`\`\`bash
sudo -u $DEPLOY_USER git clone https://github.com/AkrishConclave/rag-support.git $PROJECT_DIR
cd $PROJECT_DIR
\`\`\`

## 4. Настройка переменных окружения

\`\`\`bash
# Создаем .env файл для продакшена
sudo -u $DEPLOY_USER cp deployment/prod.env.example deployment/prod.env
sudo -u $DEPLOY_USER nano deployment/prod.env
# Заполните YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_API_KEY и остальные переменные.
\`\`\`

## 5. Первый запуск (если репозиторий уже клонирован)

\`\`\`bash
cd $PROJECT_DIR/docker
sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml up -d
\`\`\`

## 6. Проверка статуса

\`\`\`bash
sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml ps
sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml logs -f rag_api
\`\`\`

## Полезные команды

- Деплой вручную: \`sudo deploy-rag-support\`
- Просмотр логов: \`sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml logs -f\`
- Остановка: \`sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml down\`
- Перезапуск: \`sudo -u $DEPLOY_USER docker-compose -f docker-compose.prod.yml restart\`
EOF

chown $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR/DEPLOY_SETUP.md

# Вывод информации
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Сервер успешно подготовлен!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📋 Следующие шаги:${NC}"
echo ""
echo "1. Если репозиторий еще не клонирован, выполните:"
echo "   sudo -u $DEPLOY_USER git clone https://github.com/AkrishConclave/rag-support.git $PROJECT_DIR"
echo ""
echo "2. Настройте переменные окружения:"
echo "   sudo -u $DEPLOY_USER cp $PROJECT_DIR/deployment/prod.env.example $PROJECT_DIR/deployment/prod.env"
echo "   sudo -u $DEPLOY_USER nano $PROJECT_DIR/deployment/prod.env"
echo ""
echo "3. Добавьте SSH ключ для пользователя $DEPLOY_USER (для GitHub Actions)"
echo ""
echo "4. Подробная инструкция находится в:"
echo "   $PROJECT_DIR/deployment/README.md"
echo ""
echo -e "${GREEN}🎉 Готово к работе!${NC}"

