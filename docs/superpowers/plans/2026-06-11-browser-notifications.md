# План реализации: Браузерные уведомления и напоминания

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить in-page уведомления о предстоящих сменах и новых сообщениях чата, а также Service Worker fallback для offline-лагеря.

**Architecture:** Два новых API-эндпоинта отдают данные; JS в `base.html` периодически проверяет смены и слушает SSE чата; `profile.html` даёт управлять разрешениями; `sw.js` обрабатывает push/sync.

**Tech Stack:** FastAPI, Jinja2, vanilla JS, Service Worker, Browser Notification API.

---

### Task 1: API `/api/my-upcoming-shifts`

**Files:**
- Modify: `routers/profile.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notifications.py
import pytest
from datetime import date, time
from services.auth import sign_cookie, hash_password
from config import COOKIE_NAME, ROLE_VOLUNTEER
import models


class TestNotifications:
    @pytest.fixture
    def volunteer_client(self, client, test_user):
        client.cookies.set(COOKIE_NAME, sign_cookie(test_user.id))
        return client

    def test_my_upcoming_shifts(self, volunteer_client, test_user, db):
        direction = models.Direction(name="TestDir")
        db.add(direction)
        db.flush()

        slot = models.Slot(
            direction_id=direction.id,
            date=date(2030, 7, 9),
            time=time(10, 0),
            capacity=5,
        )
        db.add(slot)
        db.flush()

        db.add(models.Booking(user_id=test_user.id, slot_id=slot.id))
        db.commit()

        response = volunteer_client.get("/api/my-upcoming-shifts")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["direction"] == "TestDir"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.\venv\Scripts\python -m pytest tests/test_notifications.py::TestNotifications::test_my_upcoming_shifts -v
```

Expected: FAIL with 404

- [ ] **Step 3: Add endpoint**

```python
# routers/profile.py, after /profile/@{username}/cancel/{booking_id}
from datetime import datetime, timedelta


@router.get("/api/my-upcoming-shifts")
def my_upcoming_shifts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    now = datetime.now()
    bookings = (
        db.query(models.Booking)
        .join(models.Slot)
        .filter(models.Booking.user_id == user.id)
        .filter(models.Slot.date >= now.date())
        .order_by(models.Slot.date, models.Slot.time)
        .all()
    )
    result = []
    for b in bookings:
        slot_dt = datetime.combine(b.slot.date, b.slot.time)
        result.append({
            "slot_id": b.slot.id,
            "direction": b.slot.direction.name,
            "date": b.slot.date.isoformat(),
            "time": b.slot.time.strftime("%H:%M"),
            "datetime_iso": slot_dt.isoformat(),
        })
    return result
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.\venv\Scripts\python -m pytest tests/test_notifications.py::TestNotifications::test_my_upcoming_shifts -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_notifications.py routers/profile.py
git commit -m "feat: add /api/my-upcoming-shifts endpoint"
```

---

### Task 2: API `/api/unread-chat-count`

**Files:**
- Modify: `routers/chat.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notifications.py, inside TestNotifications
    def test_unread_chat_count(self, volunteer_client, test_user, db):
        response = volunteer_client.get("/api/unread-chat-count")
        assert response.status_code == 200
        assert response.json() == {"unread": 0}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.\venv\Scripts\python -m pytest tests/test_notifications.py::TestNotifications::test_unread_chat_count -v
```

Expected: FAIL with 404

- [ ] **Step 3: Add endpoint**

```python
# routers/chat.py
from fastapi.responses import JSONResponse


@router.get("/api/unread-chat-count")
def unread_chat_count(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    count = (
        db.query(models.ChatMessage)
        .outerjoin(
            models.ChatRead,
            (models.ChatRead.message_id == models.ChatMessage.id) &
            (models.ChatRead.user_id == user.id)
        )
        .filter(models.ChatMessage.receiver_id == user.id)
        .filter(models.ChatRead.id == None)
        .count()
    )
    return JSONResponse({"unread": count})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.\venv\Scripts\python -m pytest tests/test_notifications.py::TestNotifications::test_unread_chat_count -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_notifications.py routers/chat.py
git commit -m "feat: add /api/unread-chat-count endpoint"
```

---

### Task 3: Кнопка управления уведомлениями в профиле

**Files:**
- Modify: `templates/profile.html`

- [ ] **Step 1: Add button and JS**

After the password change block in `templates/profile.html`:

```html
<!-- Уведомления -->
<div class="bg-white rounded-2xl border border-gray-200 p-4 mb-4">
  <h3 class="text-sm font-semibold text-gray-600 mb-3">Уведомления</h3>
  <button id="notif-toggle" type="button"
    class="w-full text-sm px-4 py-2 rounded-xl transition">
    🔔 Включить уведомления
  </button>
  <p id="notif-status" class="text-xs text-gray-400 mt-2 text-center"></p>
</div>

<script>
(function() {
  const btn = document.getElementById('notif-toggle');
  const status = document.getElementById('notif-status');
  if (!btn) return;

  function updateUI() {
    if (Notification.permission === 'granted') {
      btn.textContent = '🔕 Уведомления включены';
      btn.className = 'w-full text-sm px-4 py-2 rounded-xl bg-green-100 text-green-700 transition';
      status.textContent = 'Вы будете получать напоминания о сменах и сообщениях, пока приложение открыто.';
    } else if (Notification.permission === 'denied') {
      btn.textContent = '🔒 Уведомления заблокированы';
      btn.className = 'w-full text-sm px-4 py-2 rounded-xl bg-gray-100 text-gray-500 transition';
      status.textContent = 'Разрешите уведомления в настройках браузера.';
    } else {
      btn.textContent = '🔔 Включить уведомления';
      btn.className = 'w-full text-sm px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition';
      status.textContent = '';
    }
  }

  btn.addEventListener('click', async function() {
    if (!('Notification' in window)) {
      status.textContent = 'Ваш браузер не поддерживает уведомления.';
      return;
    }
    const permission = await Notification.requestPermission();
    updateUI();
  });

  updateUI();
})();
</script>
```

- [ ] **Step 2: Verify visually**

Open `/profile` and check the notification button renders.

- [ ] **Step 3: Commit**

```bash
git add templates/profile.html
git commit -m "feat: notification permission toggle in profile"
```

---

### Task 4: Глобальные напоминания о сменах

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add JS before closing `</body>`**

```javascript
// ── Напоминания о сменах ─────────────────────────────────────────────────
(function() {
  const SHOWN_KEY = 'hatiapp_shown_reminders';

  function getShown() {
    try { return JSON.parse(localStorage.getItem(SHOWN_KEY) || '[]'); }
    catch (e) { return []; }
  }

  function markShown(slotId, minutesBefore) {
    const shown = getShown();
    shown.push(`${slotId}:${minutesBefore}`);
    // keep last 100
    while (shown.length > 100) shown.shift();
    localStorage.setItem(SHOWN_KEY, JSON.stringify(shown));
  }

  function isShown(slotId, minutesBefore) {
    return getShown().includes(`${slotId}:${minutesBefore}`);
  }

  async function checkReminders() {
    try {
      const res = await fetch('/api/my-upcoming-shifts');
      if (!res.ok) return;
      const shifts = await res.json();
      const now = new Date();

      shifts.forEach(function(s) {
        const slotTime = new Date(s.datetime_iso);
        const diffMin = (slotTime - now) / (1000 * 60);

        [24 * 60, 2 * 60].forEach(function(minutesBefore) {
          if (diffMin <= minutesBefore && diffMin > 0 && !isShown(s.slot_id, minutesBefore)) {
            const when = minutesBefore === 24 * 60 ? 'завтра' : 'через 2 часа';
            const text = `⏰ ${s.direction}: смена ${when} в ${s.time}`;
            showToast(text, 'info');
            if (Notification.permission === 'granted') {
              new Notification('HatiApp — напоминание', {
                body: text,
                icon: '/static/icon-192.png',
              });
            }
            markShown(s.slot_id, minutesBefore);
          }
        });
      });
    } catch (e) {}
  }

  if ('Notification' in window) {
    checkReminders();
    setInterval(checkReminders, 60 * 1000);
  }
})();
```

- [ ] **Step 2: Verify manually**

Create a booking 2 hours in the future, open any page, wait/check console.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: in-page shift reminders at 24h and 2h"
```

---

### Task 5: Уведомления о новых сообщениях чата

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Extend existing SSE notify handler**

In the chat SSE block (around line 507+), update `applyNotify`:

```javascript
function applyNotify(data) {
  const prevUnread = parseInt(badge.textContent || '0');
  const newUnread = data.unread || 0;

  if (newUnread > 0) {
    badge.textContent = newUnread > 9 ? '9+' : newUnread;
    badge.style.display = 'flex';
    // Show toast only if we are not on /chat page and count increased
    if (location.pathname !== '/chat' && newUnread > prevUnread) {
      const lastChat = data.chats && data.chats.find(function(c) { return c.unread > 0; });
      if (lastChat) {
        showToast('💬 Новое сообщение: ' + (lastChat.name || 'Чат'), 'info');
        if (Notification.permission === 'granted') {
          new Notification('HatiApp — сообщение', {
            body: 'Новое сообщение в чате',
            icon: '/static/icon-192.png',
          });
        }
      }
    }
  } else {
    badge.style.display = 'none';
  }
  // ... existing chat list update ...
}
```

- [ ] **Step 2: Verify manually**

Send a message to a user while they are on another page; toast should appear.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: chat message toast and notification"
```

---

### Task 6: Service Worker fallback

**Files:**
- Modify: `static/sw.js`

- [ ] **Step 1: Add push and sync handlers**

```javascript
// Push notifications from local server (offline camp mode)
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title || 'HatiApp', {
      body: data.body || '',
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      data: data,
    })
  );
});

// Background sync: trigger reminder check when connection returns
self.addEventListener('sync', (event) => {
  if (event.tag === 'check-reminders') {
    event.waitUntil(
      fetch('/api/my-upcoming-shifts', { credentials: 'include' })
        .then(r => r.json())
        .then(shifts => {
          const now = new Date();
          shifts.forEach(s => {
            const slotTime = new Date(s.datetime_iso);
            const diffMin = (slotTime - now) / (1000 * 60);
            if (diffMin > 0 && diffMin <= 2 * 60) {
              return self.registration.showNotification('HatiApp — напоминание', {
                body: `${s.direction}: смена через 2 часа в ${s.time}`,
                icon: '/static/icon-192.png',
              });
            }
          });
        })
        .catch(() => {})
    );
  }
});
```

- [ ] **Step 2: Register sync from base.html**

Add to `base.html` JS:

```javascript
if ('serviceWorker' in navigator && 'SyncManager' in window) {
  navigator.serviceWorker.ready.then(registration => {
    registration.sync.register('check-reminders').catch(() => {});
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add static/sw.js templates/base.html
git commit -m "feat: service worker push and sync fallback"
```

---

### Task 7: Full test run

- [ ] **Step 1: Run all tests**

```bash
.\venv\Scripts\python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 2: Commit if any fixes**

```bash
git add .
git commit -m "test: notification reminders test suite"
```

---

## Self-Review

- [x] Spec coverage: all sections have tasks.
- [x] Placeholder scan: no TBD/TODO.
- [x] Type consistency: `datetime_iso` used consistently.
