# Быстрый старт для демо

## Что вам понадобится

1. **Сервер**: Ubuntu 22.04 (VPS от Timeweb или любой другой)
2. **Доступ**: SSH (логин/пароль root)
3. **Файлы**: `hatiapp-deploy.zip` (в папке проекта)

## Запуск за 5 минут

### 1. Подключитесь к серверу
```bash
ssh root@ВАШ_IP
```

### 2. Установите зависимости
```bash
apt update
apt install -y python3 python3-pip python3-venv unzip
```

### 3. Загрузите проект
Используйте FileZilla или scp чтобы загрузить `hatiapp-deploy.zip` в `/opt/`

### 4. Распакуйте и запустите
```bash
cd /opt
unzip hatiapp-deploy.zip -d hatiapp
cd hatiapp

# Установка Python пакетов
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn sqlalchemy pydantic-settings python-jose passlib python-multipart jinja2 slowapi qrcode pillow

# Запуск
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5. Откройте порт
```bash
ufw allow 8000/tcp
ufw enable
```

### 6. Готово!
Откройте в браузере: `http://ВАШ_IP:8000`

---

## Тестовые аккаунты

| Логин | Пароль | Роль |
|-------|--------|------|
| ADIMA | ADIMA | Админ |
| vol1 | vol123 | Волонтёр |

---

## Что показать на демо

1. **Страница входа** - QR-код для быстрого входа
2. **Расписание** - календарь с записями
3. **Запись на смену** - выбор даты и направления
4. **Мои смены** - список записей с QR-кодами
5. **Админ панель** - управление пользователями (логин: ADIMA)

---

## После демо

Чтобы остановить сервер:
```bash
Ctrl+C  # остановить uvicorn
```

Чтобы удалить:
```bash
rm -rf /opt/hatiapp
```

---

## Помощь

Если что-то не работает:
1. Проверьте что порт 8000 открыт: `ufw status`
2. Проверьте что приложение работает: `curl http://localhost:8000`
3. Посмотрите ошибки в консоли

**Для детальной инструкции см. README-DEPLOY.md**
