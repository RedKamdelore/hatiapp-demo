# Hatiapp — Project Context

> **Читай этот файл первым** перед любыми изменениями. Он описывает архитектуру, стек, паттерны и критические решения.

---

## 1. Обзор

**Hatiapp** — веб-приложение для управления волонтёрскими сменами. Локальная сеть, ~100 одновременных пользователей (ПК, Android, iPhone). Русскоязычный интерфейс.

---

## 2. Технологический стек

| Слой | Технология | Примечание |
|------|-----------|------------|
| Backend | **Python 3.14 + FastAPI** | APIRouter, Jinja2Templates |
| ORM | **SQLAlchemy** (sync) | Не async! |
| База данных | **SQLite** (файл `app.db`) | WAL mode включён для конкурентности |
| Миграции | **Alembic** | Инициализация: `alembic upgrade head` |
| Frontend | **Jinja2 + HTML** (server-side rendering) | ❌ НЕ React, ❌ НЕ Vue, ❌ НЕ SPA |
| Стили | **Tailwind CSS** (inline utility classes) | Файл `static/tailwind.min.js` (CDN fallback) |
| JS | **Vanilla JavaScript** | IIFE паттерн, никаких фреймворков |
| Real-time | **WebSocket** (чат) + **SSE** (уведомления) | WebSocket: `/ws/chat`, SSE: `/sse/notify` |
| Auth | **Session-based** (cookies) | Токен в cookie `session_token`, ❌ НЕ JWT |
| Rate Limit | **slowapi** | 10 запросов/мин на `/login` |
| Config | **pydantic-settings** + `.env` | `SECRET_KEY` в `.env` |
| Testing | **pytest** + `TestClient` | Запуск: `pytest tests/` |

---

## 3. Архитектура проекта

```
Hatiapp/
├── main.py              # Точка входа: app = FastAPI(), подключение роутеров
├── config.py            # Настройки, StrEnum ролей, pydantic Settings
├── database.py          # SQLite engine (WAL mode, pool_pre_ping), SessionLocal, get_db
├── models.py            # SQLAlchemy models (User, Slot, Booking, ChatMessage, ...)
├── schemas.py           # Pydantic models для валидации
├── services/            # Бизнес-логика
│   ├── auth.py          # Хеширование паролей, get_current_user
│   ├── booking.py       # book_slot() с SELECT FOR UPDATE + retry
│   ├── websocket.py     # WebSocket connection manager
│   ├── sse_manager.py   # SSE push manager
│   ├── rate_limit.py    # Rate limiter (slowapi)
│   ├── export.py        # Excel export
│   └── import_users.py  # Импорт пользователей из Excel
├── routers/             # HTTP маршруты (FastAPI APIRouter)
│   ├── auth.py          # /login, /logout
│   ├── schedule.py      # /schedule, /book/{id}, /cancel/{id}
│   ├── chat.py          # /chat, /ws/chat (WebSocket)
│   ├── admin.py         # /admin/*
│   ├── sse.py           # /sse/notify, /api/schedule-data
│   ├── logs.py          # /logs/*
│   ├── profile.py       # /me, /profile/*
│   ├── leader.py        # /leader/*
│   └── slots.py         # /admin/slots
├── templates/           # Jinja2 HTML шаблоны
│   ├── base.html        # Базовый шаблон: навигация, toast, SSE client
│   ├── schedule.html    # Таблица расписания
│   ├── slots.html       # Карточки слотов с кнопками записи
│   ├── chat.html        # Чат (для волонтёров и лотоса в диалоге)
│   ├── chat_lotos.html  # Список диалогов лотоса
│   └── admin.html       # Админ-панель
├── static/              # Статические файлы
│   ├── tailwind.min.js
│   ├── favicon.svg
│   └── manifest.json    # PWA manifest (без Service Worker!)
├── tests/               # pytest
│   ├── conftest.py      # TestClient, in-memory SQLite, fixtures
│   ├── test_auth.py     # 6 тестов авторизации
│   └── test_booking.py  # Тесты бронирования и schedule
├── seed/                # Скрипты начального заполнения
├── alembic/             # Миграции Alembic
└── .env                 # SECRET_KEY (в .gitignore!)
```

### 3.1 Паттерн Dependency Injection

```python
# Каждый роутер использ:
def handler(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)  # Из cookie
    ...
```

### 3.2 Формат ответов

- **HTML страницы**: `templates.TemplateResponse("template.html", {...})`
- **Редиректы с toast**: `RedirectResponse("/route?toast=Сообщение&toast_type=success")`
- **JSON API**: только для polling (`/api/schedule-data`, `/api/slot-data/{id}`)

---

## 4. Ключевые паттерны и соглашения

### 4.1 Frontend (❌ НЕ SPA!)

- **Server-side rendering** через Jinja2
- **Tailwind utility classes** напрямую в HTML (`class="bg-white rounded-xl ..."`)
- **Vanilla JS** внутри `<script>` тегов шаблонов
- **IIFE паттерн** для изоляции scope:
  ```javascript
  (function() {
    // локальные переменные
  })();
  ```
- **Polling fallback**: schedule и slots опрашивают API каждые 10 сек
- **No optimistic UI**: честные состояния загрузки (`⟳ Записываем...`)

### 4.2 Toast-уведомления

```python
# Сервер
return RedirectResponse(f"/schedule?toast=Записано!&toast_type=success")

# Клиент (base.html) — автоматически показывает и очищает URL
```

### 4.3 WebSocket чат

- Авторизация по cookie (fallback на `?token=` в query)
- Авто-переподключение каждые 3 секунды
- Сообщение формата: `{"action": "send", "text": "...", "receiver_id": N}`

### 4.4 Бронирование (Race condition protection)

```python
# services/booking.py
# SELECT FOR UPDATE + retry с экспоненциальным backoff
with db.begin():
    slot = db.query(Slot).filter_by(id=slot_id).with_for_update().first()
    # проверка лимитов
    db.add(Booking(...))
```

### 4.5 SQL-индексы

Все внешние ключи и часто используемые поля проиндексированы (миграция `indexes`).

---

## 5. Модели данных (основные)

```python
# models.py
class User:
    id, username, full_name, password_hash, role (admin|leader|lotos|volunteer)
    avatar, is_active, created_at

class Direction:
    id, name
    leaders → DirectionLeader[]

class DirectionLeader:
    direction_id, user_id  # составной PK

class Slot:
    id, direction_id, date, time, capacity

class Booking:
    id, user_id, slot_id, created_at

class ChatMessage:
    id, sender_id, receiver_id, text, created_at

class ChatRead:
    id, user_id, other_id, read_at  # для отслеживания прочтения

class BlockedDay:
    id, date (unique)  # заблокированные для записи дни
```

---

## 6. Критические архитектурные решения

| Решение | Причина |
|---------|---------|
| ❌ **Нет CSRF** | `starlette-csrf` ломался на HTTP локальной сети, блокировал логин. Защита: rate limiting |
| ❌ **Нет Service Worker** | Кэшировал битые ответы, вызывал чёрные экраны. PWA manifest оставлен только для иконки |
| ❌ **Нет optimistic UI** | Пользователь предпочитает честное "Записываем..." с disabled кнопкой |
| ✅ **SQLite WAL mode** | Для ~100 concurrent users без миграции на PostgreSQL |
| ✅ **SSE вместо polling** | Уведомления (badge счётчик) через `/sse/notify` |
| ✅ **Session-based auth** | Простота, работает без JS |
| ✅ **Local network only** | Нет HTTPS, нет интернета |

---

## 7. API Endpoints (ключевые)

```
GET  /schedule                  → schedule.html (таблица)
GET  /schedule/{dir_id}/{date}  → slots.html (карточки слотов)
POST /book/{slot_id}            → Redirect с toast
POST /cancel/{booking_id}       → Redirect с toast
GET  /chat                      → chat.html или chat_lotos.html
GET  /chat/with/{user_id}       → chat.html (диалог лотоса)
WS   /ws/chat                   → WebSocket real-time
GET  /sse/notify                → SSE уведомления
GET  /api/schedule-data         → JSON для polling
GET  /api/slot-data/{slot_id}   → JSON для polling
POST /chat/read/{other_id}      → Отметить прочитанным
```

---

## 8. Тестирование

```bash
# Запуск
$env:PYTHONPATH="."; pytest tests/ -v

# Структура тестов
- test_auth.py: login/logout, редиректы, защита роутов
- test_booking.py: book/cancel/stats, schedule/slots endpoints
```

---

## 9. Запуск проекта

```bash
# 1. Зависимости
pip install -r requirements.txt

# 2. База данных (первая установка)
alembic upgrade head

# 3. Сид данных
python seed/run.py

# 4. Запуск
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Дефолтные пользователи:** `ADIMA`/`ADIMA` (admin), `vol1`/`vol123`, `leader1`/`leader123`, `lotos`/`lotos123`

---

## 10. Частые ошибки и решения

| Проблема | Решение |
|----------|---------|
| Чёрный экран после навигации | Отменить Service Worker регистрацию (есть скрипт в base.html) |
| Форма не отправляется | Проверить `type="submit"` на кнопках (был баг в slots.html) |
| Race condition при записи | `SELECT FOR UPDATE` + retry в `services/booking.py` |
| Нет toast после redirect | Проверить query params: `?toast=...&toast_type=success` |

---

## 11. Для AI-ассистента

**Если тебя просят изменить frontend:**
- НЕ предлагай React/Vue/SPA
- Используй Jinja2 + Tailwind + vanilla JS
- Следи за `type="submit"` на кнопках в формах
- Добавляй polling для динамических данных (если не WebSocket/SSE)

**Если тебя просят изменить backend:**
- Используй sync SQLAlchemy (не async!)
- Для записи в БД с конкурентностью — `with_for_update()` + retry
- Auth через `get_current_user(request, db)` (cookie-based)
- Toast-уведомления через redirect с query params

**Если тебя просят добавить real-time:**
- Чат → WebSocket (`/ws/chat`)
- Badge/уведомления → SSE (`/sse/notify`)
- Обновление данных → polling каждые 10 сек (fallback)

**Никогда НЕ добавляй:**
- Service Worker / PWA кэширование
- CSRF (не работает на HTTP локальной сети)
- Optimistic UI без явного запроса пользователя
