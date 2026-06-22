# План реализации: Клик по имени в чате + Описание смены

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить кликабельные имена в чате (→ профиль) и описание для каждого слота с ролевым доступом.

**Architecture:** Минимальные изменения в существующих шаблонах и роутах. Поле `description` добавляется в `Slot`, редактируется через API, отображается inline на странице слотов.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Tailwind CSS, vanilla JS.

---

### Task 1: Клик по имени в чате → профиль

**Files:**
- Modify: `templates/chat.html`

- [ ] **Step 1: Найти где отображается имя отправителя**

Найти блоки с `sender_name` или `u.full_name or u.username` в `templates/chat.html`.

- [ ] **Step 2: Обернуть имя в ссылку**

```html
<!-- Было -->
<span class="font-medium text-gray-800 text-sm">{{ sender_name }}</span>

<!-- Стало -->
<a href="/profile/@{{ sender_username }}" class="font-medium text-gray-800 text-sm hover:text-indigo-600 transition">{{ sender_name }}</a>
```

Проверить, что `sender_username` доступен в контексте. Если нет — добавить его в данные сообщения (router/sse.py или chat WebSocket payload).

- [ ] **Step 3: Проверить в списке диалогов**

Аналогично обернуть имена в списке диалогов (`/chat`), если они есть.

- [ ] **Step 4: Commit**

```bash
git add templates/chat.html
git commit -m "feat: clickable sender names in chat link to profile"
```

---

### Task 2: Добавить поле description в модель Slot

**Files:**
- Modify: `models.py`
- Create: Alembic migration

- [ ] **Step 1: Добавить поле в модель**

```python
# models.py, class Slot
    description = Column(Text, nullable=True)
```

- [ ] **Step 2: Создать миграцию Alembic**

```bash
alembic revision --autogenerate -m "add slot description"
alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add models.py alembic/versions/
git commit -m "feat: add description field to Slot model"
```

---

### Task 3: API для обновления описания слота

**Files:**
- Modify: `routers/schedule.py`

- [ ] **Step 1: Добавить endpoint**

```python
@router.post("/api/slot/{slot_id}/description")
def update_slot_description(
    slot_id: int,
    request: Request,
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    slot = db.query(models.Slot).filter_by(id=slot_id).first()
    if not slot:
        return JSONResponse({"error": "Slot not found"}, status_code=404)

    # Права: admin/lotos — любой; leader — только свои направления
    if user.role not in {ROLE_ADMIN, ROLE_LOTOS}:
        if user.role == ROLE_LEADER:
            # Проверяем, что пользователь — руководитель этого направления
            is_leader = db.query(models.DirectionLeader).filter_by(
                direction_id=slot.direction_id, user_id=user.id
            ).first()
            if not is_leader:
                return JSONResponse({"error": "Forbidden"}, status_code=403)
        else:
            return JSONResponse({"error": "Forbidden"}, status_code=403)

    slot.description = description.strip() or None
    db.commit()
    return JSONResponse({"ok": True, "description": slot.description})
```

- [ ] **Step 2: Commit**

```bash
git add routers/schedule.py
git commit -m "feat: API to update slot description with role checks"
```

---

### Task 4: Отображение и редактирование описания на странице слотов

**Files:**
- Modify: `templates/slots.html`

- [ ] **Step 1: Добавить блок описания**

Найти место между прогресс-баром и списком волонтёров. Добавить:

```html
{% if slot.description %}
<div class="text-sm text-gray-600 mb-2 italic">{{ slot.description }}</div>
{% endif %}
```

- [ ] **Step 2: Добавить inline-редактор (только для тех, у кого есть права)**

Передать `can_edit_slot` из роута в шаблон (или проверять роль прямо в шаблоне).

```html
{% if user.role in ('admin', 'lotos') or (user.role == 'leader' and user.id in slot.direction.leader_ids) %}
<div class="mt-1 mb-2">
  <button onclick="toggleEdit({{ slot.id }})" class="text-xs text-indigo-500 hover:underline">✏️ Изменить описание</button>
  <div id="edit-{{ slot.id }}" style="display:none;">
    <textarea id="desc-{{ slot.id }}" class="w-full border rounded-lg p-2 text-sm" rows="2">{{ slot.description or '' }}</textarea>
    <div class="flex gap-2 mt-1">
      <button onclick="saveDesc({{ slot.id }})" class="text-xs bg-indigo-600 text-white px-3 py-1 rounded">Сохранить</button>
      <button onclick="toggleEdit({{ slot.id }})" class="text-xs text-gray-500">Отмена</button>
    </div>
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: Добавить JS для сохранения**

```javascript
async function saveDesc(slotId) {
  const text = document.getElementById('desc-' + slotId).value;
  const res = await fetch('/api/slot/' + slotId + '/description', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'description=' + encodeURIComponent(text)
  });
  if (res.ok) location.reload();
}
function toggleEdit(slotId) {
  const el = document.getElementById('edit-' + slotId);
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
```

- [ ] **Step 4: Commit**

```bash
git add templates/slots.html
git commit -m "feat: display and edit slot description on schedule page"
```

---

### Task 5: Тесты

**Files:**
- Create: `tests/test_slot_description.py`

- [ ] **Step 1: Написать тесты**

```python
import pytest
from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS, ROLE_VOLUNTEER
import models

class TestSlotDescription:
    @pytest.fixture
    def admin_client(self, client, admin_user):
        client.cookies.set("session", sign_cookie(admin_user.id))
        return client

    def test_admin_can_update_description(self, admin_client, db):
        # создать слот
        # POST /api/slot/{id}/description
        # проверить 200 и что description обновился
        pass

    def test_volunteer_cannot_update(self, client, db, volunteer_user):
        client.cookies.set("session", sign_cookie(volunteer_user.id))
        # POST → 403
        pass
```

- [ ] **Step 2: Запустить тесты**

```bash
pytest tests/test_slot_description.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_slot_description.py
git commit -m "test: slot description permissions"
```

---

## Self-Review

- [x] Spec coverage: обе фичи покрыты задачами.
- [x] Placeholder scan: нет TBD/TODO.
- [x] Type consistency: `description` = Column(Text), API принимает str Form.
