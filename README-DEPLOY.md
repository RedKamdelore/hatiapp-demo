# HatiApp - VPS Deployment Guide

## Быстрый старт (для демо)

### Шаг 1: Регистрация на Timeweb Cloud

1. Откройте [timeweb.cloud](https://timeweb.cloud)
2. Зарегистрируйтесь (можно через Telegram или email)
3. Подтвердите email

### Шаг 2: Создание сервера

1. В панели управления нажмите "Создать сервер"
2. Выберите:
   - **ОС**: Ubuntu 22.04 LTS
   - **Тариф**: Cloud-1 (1 CPU, 1GB RAM, 15GB SSD) - 200₽/месяц
   - **Локация**: Москва (ближе к вам)
3. Нажмите "Создать"
4. **Подождите 2-3 минуты** пока сервер запустится

### Шаг 3: Подключение к серверу

1. В панели Timeweb найдите ваш сервер
2. Скопируйте **IP-адрес** (например: `185.123.45.67`)
3. Скопируйте **пароль root**

**Подключение через Windows (PowerShell):**
```powershell
ssh root@ВАШ_IP
# Введите пароль root когда спросит
```

### Шаг 4: Установка HatiApp

**На сервере выполните:**

```bash
# Скачать установщик
curl -O https://raw.githubusercontent.com/ВАШ_РЕПОЗИТОРИЙ/main/deploy-vps.sh

# Или загрузите файлы через SFTP (FileZilla)

# Запустить установку
bash deploy-vps.sh
```

**Или вручную:**
```bash
# 1. Обновить систему
apt update && apt install -y python3 python3-pip python3-venv nginx sqlite3

# 2. Создать папку приложения
mkdir -p /opt/hatiapp
cd /opt/hatiapp

# 3. Загрузить файлы (через SFTP или wget)
# Используйте FileZilla для загрузки hatiapp-deploy.zip

# 4. Распаковать
apt install -y unzip
unzip hatiapp-deploy.zip

# 5. Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn sqlalchemy pydantic-settings python-jose passlib python-multipart jinja2 slowapi qrcode pillow

# 6. Запустить
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Шаг 5: Открыть порт

```bash
# Разрешить порт 8000
ufw allow 8000/tcp
ufw allow 80/tcp
ufw enable
```

### Шаг 6: Автозапуск (опционально)

```bash
# Создать сервис
cat > /etc/systemd/system/hatiapp.service << 'EOF'
[Unit]
Description=HatiApp
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/hatiapp
ExecStart=/opt/hatiapp/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hatiapp
systemctl start hatiapp
```

### Шаг 7: Готово!

Откройте в браузере:
```
http://ВАШ_IP:8000
```

**Тестовые данные:**
- Логин: `ADIMA`
- Пароль: `ADIMA`
- Логин: `vol1`
- Пароль: `vol123`

---

## Загрузка файлов на сервер

### Способ 1: FileZilla (рекомендуется)

1. Скачайте FileZilla Client
2. Подключитесь:
   - Хост: `sftp://ВАШ_IP`
   - Логин: `root`
   - Пароль: ваш пароль root
   - Порт: 22
3. Перетащите файлы проекта в `/opt/hatiapp`

### Способ 2: Командная строка

```bash
# На вашем компьютере (Windows PowerShell):
scp -r C:\Users\...\Hatiapp_cowork_OPENCODE\* root@ВАШ_IP:/opt/hatiapp/
```

---

## Управление сервером

```bash
# Проверить статус
systemctl status hatiapp

# Перезапустить
systemctl restart hatiapp

# Посмотреть логи
journalctl -u hatiapp -f

# Остановить
systemctl stop hatiapp
```

---

## Для демо (3 дня бесплатно)

Timeweb даёт **200₽ на баланс** при регистрации. Этого хватит на 3 дня работы сервера Cloud-1.

После демо:
- Удалите сервер (чтобы не списывались деньги)
- Или пополните баланс на 200₽/мес

---

## Проблемы?

**Не открывается сайт:**
```bash
# Проверить firewall
ufw status

# Проверить что приложение работает
curl http://localhost:8000

# Проверить логи
journalctl -u hatiapp -n 50
```

**Ошибка 500:**
```bash
# Посмотреть логи приложения
cd /opt/hatiapp
source venv/bin/activate
python -c "from main import app; print('OK')"
```

---

## Готовый архив

Файл `hatiapp-deploy.zip` содержит:
- Весь исходный код
- Статические файлы (CSS, JS)
- Шаблоны HTML
- Скрипт установки

**Вес архива:** ~10-15 MB (без venv и БД)

---

Если что-то не получается — пишите, помогу!
