# Admin Improvements v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add mobile mass actions, audit logging, URL-based filter state, and direction management to the admin panel.

**Architecture:** A new `AdminActionLog` model captures every mass action. Backend endpoints in `routers/admin.py` handle audit logging, direction CRUD, and action-log pagination. Frontend changes in `templates/admin.html` add mobile checkboxes/bottom bar, URL filter sync, and direction edit/delete modals. A new `templates/action_logs.html` renders the audit log page.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy, Alembic, SQLite, vanilla JS, Tailwind.

---

## File Structure

- `models.py` — add `AdminActionLog` model
- `alembic/versions/2026_06_15_add_admin_action_logs.py` — Alembic migration
- `routers/admin.py` — audit write, `/admin/action-logs`, `/admin/direction/{id}/edit`, `/admin/direction/{id}/delete-info`
- `templates/admin.html` — mobile checkboxes, bottom action bar, URL filter sync, direction modals
- `templates/action_logs.html` — new audit log page
- `tests/test_admin_audit_logs.py` — audit log tests
- `tests/test_admin_directions.py` — direction edit/delete tests
- `tests/test_admin_filters_url.py` — filter URL sync smoke test
- `tests/test_admin_mobile_mass_actions.py` — mobile mass-action markup test

---

## Task 1: Add AdminActionLog model and Alembic migration

**Files:**
- Modify: `models.py`
- Create: `alembic/versions/2026_06_15_add_admin_action_logs.py`

- [ ] **Step 1: Write the model**

In `models.py`, after `LoginLog`:
```python
class AdminActionLog(Base):
    """Audit log for mass admin actions."""
    __tablename__ = "admin_action_logs"

    id           = Column(Integer, primary_key=True)
    admin_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action       = Column(String, nullable=False, index=True)
    target_count = Column(Integer, nullable=False, default=0)
    details      = Column(Text, nullable=True)
    ip_address   = Column(String, nullable=True)
    user_agent   = Column(String, nullable=True)
    created_at   = Column(DateTime, server_default=func.now(), index=True)

    admin = relationship("User")
```

- [ ] **Step 2: Generate migration via Alembic**

Run:
```bash
python -m alembic revision --autogenerate -m "add_admin_action_logs"
```

Verify the generated file creates `admin_action_logs` table with the correct columns and indexes.

- [ ] **Step 3: Apply migration**

Run:
```bash
python -m alembic upgrade head
```

Expected: success

- [ ] **Step 4: Run existing tests**

Run: `python -m pytest tests/ -q`
Expected: all pass

---

## Task 2: Write audit log on mass actions

**Files:**
- Modify: `routers/admin.py`

- [ ] **Step 1: Add helper to extract client IP**

At module level, add:
```python
def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
```

- [ ] **Step 2: Update `mass_action_users` to log action**

Before the final `db.commit()` in `mass_action_users`, after computing `count`, add:
```python
import json
log_details = {
    "user_ids": user_ids,
}
if action == "change_role":
    log_details["new_role"] = new_role
elif action in ("add_to_direction", "remove_from_direction"):
    log_details["direction_id"] = direction_id

db.add(models.AdminActionLog(
    admin_id=user.id,
    action=action,
    target_count=count,
    details=json.dumps(log_details, ensure_ascii=False),
    ip_address=_get_client_ip(request),
    user_agent=request.headers.get("user-agent", ""),
))
```

Note: `user` is the admin returned by `require_role`. If the variable is named differently in the actual code, use the correct name.

- [ ] **Step 3: Run audit tests later**

This task is verified in Task 7.

---

## Task 3: Add `/admin/action-logs` page

**Files:**
- Modify: `routers/admin.py`
- Create: `templates/action_logs.html`

- [ ] **Step 1: Add route**

In `routers/admin.py`:
```python
@router.get("/admin/action-logs", response_class=HTMLResponse)
def action_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    require_role(request, db, ROLE_ADMIN)
    per_page = 50
    offset = (page - 1) * per_page

    logs = db.query(models.AdminActionLog).options(
        joinedload(models.AdminActionLog.admin)
    ).order_by(models.AdminActionLog.created_at.desc()).offset(offset).limit(per_page).all()

    total = db.query(func.count(models.AdminActionLog.id)).scalar()
    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("action_logs.html", {
        "request": request,
        "logs": logs,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })
```

- [ ] **Step 2: Create template**

Create `templates/action_logs.html`:
```html
{% extends "base.html" %}
{% block title %}История действий{% endblock %}

{% block content %}
<div class="mb-6 flex items-center justify-between">
  <h1 class="text-xl font-bold text-gray-800">История действий</h1>
  <a href="/admin" class="text-sm text-indigo-600 hover:text-indigo-700">← Назад в админку</a>
</div>

<div class="panel-card overflow-hidden">
  <div class="panel-header">
    <span class="panel-title">📋 Массовые действия</span>
    <span class="text-xs text-gray-500">{{ total }} записей</span>
  </div>
  <div class="overflow-x-auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>Время</th>
          <th>Админ</th>
          <th>Действие</th>
          <th>Обработано</th>
          <th>Детали</th>
          <th>IP</th>
        </tr>
      </thead>
      <tbody>
        {% for log in logs %}
        <tr>
          <td class="text-xs text-gray-500 whitespace-nowrap">{{ log.created_at.strftime('%d.%m.%Y %H:%M') }}</td>
          <td>{{ log.admin.full_name or log.admin.username }}</td>
          <td>{{ log.action }}</td>
          <td class="text-center">{{ log.target_count }}</td>
          <td class="text-xs text-gray-500 max-w-xs truncate" title="{{ log.details }}">{{ log.details or '—' }}</td>
          <td class="text-xs text-gray-500">{{ log.ip_address or '—' }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {% if total_pages > 1 %}
  <div class="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
    {% if page > 1 %}
    <a href="?page={{ page - 1 }}" class="text-sm text-indigo-600 hover:text-indigo-700">← Назад</a>
    {% else %}
    <span class="text-sm text-gray-400">← Назад</span>
    {% endif %}

    <span class="text-sm text-gray-600">Страница {{ page }} из {{ total_pages }}</span>

    {% if page < total_pages %}
    <a href="?page={{ page + 1 }}" class="text-sm text-indigo-600 hover:text-indigo-700">Вперёд →</a>
    {% else %}
    <span class="text-sm text-gray-400">Вперёд →</span>
    {% endif %}
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Add link in admin panel**

In `templates/admin.html`, in the "Быстрые действия" sidebar block, add:
```html
<a href="/admin/action-logs" class="action-btn">
  <span>📋</span> История действий
</a>
```

- [ ] **Step 4: Verify route renders**

Run: `python -m pytest tests/test_admin_audit_logs.py -v` (tests created in Task 7).
Expected: PASS

---

## Task 4: Add mobile mass-action UI

**Files:**
- Modify: `templates/admin.html`

- [ ] **Step 1: Add checkboxes to mobile cards**

In the mobile card loop (around `.mobile-user-card`), change the top flex container to include a checkbox:
```html
<div class="flex items-center gap-2 mb-2">
  <input type="checkbox" name="user_ids" value="{{ u.id }}" class="user-checkbox mobile-user-checkbox rounded border-gray-300 text-indigo-600 focus:ring-indigo-400">
  ... existing avatar/content ...
</div>
```

- [ ] **Step 2: Add "select all" checkbox to mobile panel header**

Change the mobile panel header (around line 649) to:
```html
<div class="panel-header">
  <div class="flex items-center gap-2">
    <input type="checkbox" id="mobile-select-all" class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-400">
    <span class="panel-title">👥 Пользователи</span>
  </div>
  <span class="text-xs text-gray-400" id="mobile-user-count-label"></span>
</div>
```

- [ ] **Step 3: Add fixed bottom action bar**

After the mobile users panel closing `</div>`, add:
```html
<div id="mobile-mass-actions" class="sm:hidden hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-2 z-50 shadow-lg">
  <div class="flex items-center justify-between mb-2">
    <span class="text-xs text-gray-500">Выбрано: <span id="mobile-mass-count">0</span></span>
    <button type="button" id="mobile-mass-close" class="text-xs text-gray-400">✕</button>
  </div>
  <div class="grid grid-cols-3 gap-2">
    <button type="button" data-action="activate" class="mass-btn text-xs px-2 py-2 rounded-lg border border-green-200 text-green-600 bg-green-50">✅ Акт.</button>
    <button type="button" data-action="deactivate" class="mass-btn text-xs px-2 py-2 rounded-lg border border-yellow-200 text-yellow-600 bg-yellow-50">🔒 Деакт.</button>
    <button type="button" data-action="delete" class="mass-btn text-xs px-2 py-2 rounded-lg border border-red-200 text-red-500 bg-red-50">✕ Удал.</button>
  </div>
  <div class="grid grid-cols-2 gap-2 mt-2">
    <select id="mobile-mass-new-role" class="border border-gray-200 rounded-lg px-2 py-1.5 text-xs">
      <option value="" disabled selected>Роль</option>
      <option value="leader">Рук.</option>
      <option value="lotos">Лотос</option>
      <option value="volunteer">Вол.</option>
      <option value="permanent">Бессм.</option>
    </select>
    <button type="button" data-action="change_role" class="mass-btn text-xs px-2 py-1.5 rounded-lg border border-indigo-200 text-indigo-600 bg-indigo-50">📝 Роль</button>
  </div>
  <div class="grid grid-cols-2 gap-2 mt-2">
    <select id="mobile-mass-direction" class="border border-gray-200 rounded-lg px-2 py-1.5 text-xs">
      <option value="" disabled selected>Направл.</option>
      {% for d in directions %}
      <option value="{{ d.id }}">{{ d.name }}</option>
      {% endfor %}
    </select>
    <div class="flex gap-2">
      <button type="button" data-action="add_to_direction" class="mass-btn flex-1 text-xs px-2 py-1.5 rounded-lg border border-blue-200 text-blue-600 bg-blue-50">➕</button>
      <button type="button" data-action="remove_from_direction" class="mass-btn flex-1 text-xs px-2 py-1.5 rounded-lg border border-orange-200 text-orange-600 bg-orange-50">➖</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Update JS to handle mobile checkboxes and bottom bar**

Extend the mass-action IIFE:
```javascript
(function() {
  const selectAll = document.getElementById('select-all');
  const mobileSelectAll = document.getElementById('mobile-select-all');
  const checkboxes = document.querySelectorAll('.user-checkbox');
  const massBar = document.getElementById('mass-actions');
  const mobileMassBar = document.getElementById('mobile-mass-actions');
  const massCount = document.getElementById('mass-count');
  const mobileMassCount = document.getElementById('mobile-mass-count');
  const hiddenForm = document.getElementById('mass-action-form');
  const actionInput = document.getElementById('mass-action-input');

  function updateMassBar() {
    const checked = document.querySelectorAll('.user-checkbox:checked');
    if (massCount) massCount.textContent = checked.length;
    if (mobileMassCount) mobileMassCount.textContent = checked.length;
    if (massBar) massBar.classList.toggle('hidden', checked.length === 0);
    if (mobileMassBar) mobileMassBar.classList.toggle('hidden', checked.length === 0);
  }

  function setAllChecked(checked) {
    checkboxes.forEach(cb => cb.checked = checked);
    updateMassBar();
  }

  if (selectAll) selectAll.addEventListener('change', () => setAllChecked(selectAll.checked));
  if (mobileSelectAll) mobileSelectAll.addEventListener('change', () => setAllChecked(mobileSelectAll.checked));

  checkboxes.forEach(cb => cb.addEventListener('change', updateMassBar));

  const mobileClose = document.getElementById('mobile-mass-close');
  if (mobileClose) {
    mobileClose.addEventListener('click', () => setAllChecked(false));
  }

  // ... rest of existing click handler, but make secondary value lookup aware of mobile selects
})();
```

- [ ] **Step 5: Make mass-action handler read mobile secondary selects**

Change the secondary-value lookup in the click handler to:
```javascript
if (action === 'change_role') {
  const select = document.getElementById('mass-new-role') || document.getElementById('mobile-mass-new-role');
  if (!select || !select.value) { alert('Выберите роль'); return; }
  extraName = 'new_role';
  extraValue = select.value;
} else if (action === 'add_to_direction' || action === 'remove_from_direction') {
  const select = document.getElementById('mass-direction') || document.getElementById('mobile-mass-direction');
  if (!select || !select.value) { alert('Выберите направление'); return; }
  extraName = 'direction_id';
  extraValue = select.value;
}
```

- [ ] **Step 6: Prevent card navigation when clicking checkbox**

In `goToProfile`, add checkbox to the excluded selectors:
```javascript
function goToProfile(event, url) {
  if (event.target.closest('button, a, form, select, input[type="checkbox"]')) return;
  window.location.href = url;
}
```

- [ ] **Step 7: Verify mobile markup**

Run: `python -m pytest tests/test_admin_mobile_mass_actions.py -v` (Task 7).
Expected: PASS

---

## Task 5: Sync filter state with URL

**Files:**
- Modify: `templates/admin.html`

- [ ] **Step 1: Read filters from URL on load**

Add helper functions before `applyFilters`:
```javascript
function getUrlParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) || '';
}

function setUrlParams(params) {
  const url = new URL(window.location.href);
  Object.entries(params).forEach(([key, value]) => {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  });
  window.history.replaceState({}, '', url.toString());
}
```

- [ ] **Step 2: Apply URL params to controls**

Add initialization after controls exist:
```javascript
function initFiltersFromURL() {
  const q = getUrlParam('q');
  const role = getUrlParam('role');
  const status = getUrlParam('status');
  const direction = getUrlParam('direction');

  const setIfExists = (id, value) => {
    const el = document.getElementById(id);
    if (el && value) el.value = value;
  };

  setIfExists('user-search', q);
  setIfExists('mobile-user-search', q);
  setIfExists('filter-role', role);
  setIfExists('mobile-filter-role', role);
  setIfExists('filter-status', status);
  setIfExists('mobile-filter-status', status);
  setIfExists('filter-direction', direction);
  setIfExists('mobile-filter-direction', direction);

  applyFilters();
}
```

Call `initFiltersFromURL()` after it is defined.

- [ ] **Step 3: Write URL on filter change**

At the end of `applyFilters`, add:
```javascript
setUrlParams({
  q: q,
  role: role,
  status: status,
  direction: direction,
});
```

- [ ] **Step 4: Preserve filters in sort links**

Change sort links to preserve existing query params. For example:
```html
<a href="?{{ request.query_params | replace_sort('sort', 'name_asc') }}" ...>
```

If Jinja doesn't have a custom filter, construct the URL in JS or keep it simple by appending `sort` while preserving other params in the template. A minimal approach: use a small Jinja macro or helper that renders the current query string with a replaced `sort` parameter.

Add a helper filter or macro in `templates/admin.html`:
```jinja2
{% macro sort_link(current, target) %}
  {% set params = request.query_params.mutablecopy() %}
  {% set _ = params.__setitem__('sort', target) %}
  ?{{ params | urlencode }}
{% endmacro %}
```

Then use `{{ sort_link(current_sort, 'name_asc') }}` in the table headers.

- [ ] **Step 5: Verify URL sync**

Run: `python -m pytest tests/test_admin_filters_url.py -v` (Task 7).
Expected: PASS

---

## Task 6: Add direction edit/delete UI and endpoints

**Files:**
- Modify: `routers/admin.py`
- Modify: `templates/admin.html`

- [ ] **Step 1: Add edit endpoint**

In `routers/admin.py`:
```python
@router.post("/admin/direction/{direction_id}/edit")
def edit_direction(
    direction_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
):
    require_role(request, db, ROLE_ADMIN)
    d = db.query(models.Direction).filter_by(id=direction_id).first()
    if not d:
        return RedirectResponse("/admin?toast=Направление+не+найдено&toast_type=error", status_code=302)

    name = name.strip()
    if not name:
        return RedirectResponse("/admin?toast=Название+обязательно&toast_type=error", status_code=302)

    duplicate = db.query(models.Direction).filter(
        models.Direction.name == name,
        models.Direction.id != direction_id,
    ).first()
    if duplicate:
        return RedirectResponse("/admin?toast=Направление+с+таким+названием+уже+есть&toast_type=error", status_code=302)

    d.name = name
    d.description = description.strip() or None
    db.commit()
    return RedirectResponse("/admin?toast=Направление+обновлено&toast_type=success", status_code=302)
```

- [ ] **Step 2: Add delete-info endpoint**

```python
@router.get("/admin/direction/{direction_id}/delete-info")
def direction_delete_info(
    direction_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_role(request, db, ROLE_ADMIN)
    d = db.query(models.Direction).filter_by(id=direction_id).first()
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)

    slots = db.query(models.Slot).filter_by(direction_id=direction_id).all()
    slot_ids = [s.id for s in slots]

    bookings_count = 0
    if slot_ids:
        bookings_count = db.query(models.Booking).filter(models.Booking.slot_id.in_(slot_ids)).count()

    leaders_count = db.query(models.DirectionLeader).filter_by(direction_id=direction_id).count()
    prefs_count = db.query(models.UserPreference).filter_by(direction_id=direction_id).count()

    return JSONResponse({
        "name": d.name,
        "slots_count": len(slots),
        "bookings_count": bookings_count,
        "leaders_count": leaders_count,
        "prefs_count": prefs_count,
    })
```

- [ ] **Step 3: Add direction list to right sidebar**

In `templates/admin.html`, add a new sidebar card after "Распределение по ролям":
```html
<!-- ── Направления ── -->
<div class="sidebar-card">
  <div class="sidebar-title">
    <span>🧭</span> Направления
  </div>
  <div class="space-y-2">
    {% for d in directions %}
    <div class="flex items-center justify-between group">
      <span class="text-sm text-gray-700 truncate" title="{{ d.description or '' }}">{{ d.name }}</span>
      <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
        <button type="button" onclick="openEditDirectionModal({{ d.id }}, '{{ d.name | e }}', '{{ (d.description or '') | e }}')"
          class="text-xs px-1.5 py-1 rounded border border-gray-200 text-gray-500 hover:bg-gray-50">✏️</button>
        <button type="button" onclick="openDeleteDirectionModal({{ d.id }}, '{{ d.name | e }}')"
          class="text-xs px-1.5 py-1 rounded border border-red-200 text-red-500 hover:bg-red-50">🗑️</button>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
```

- [ ] **Step 4: Add modals for edit and delete**

In `templates/admin.html` inside `{% block modals %}` or after the main content:
```html
{% block modals %}
{{ super() }}

<!-- Modal: Edit direction -->
<div id="edit-direction-modal" class="fixed inset-0 bg-black/50 z-50 hidden flex items-center justify-center p-4">
  <div class="bg-white rounded-2xl w-full max-w-md p-6 shadow-xl">
    <h3 class="text-lg font-semibold text-gray-800 mb-4">Редактировать направление</h3>
    <form method="post" id="edit-direction-form" class="space-y-4">
      <input type="hidden" name="direction_id" id="edit-direction-id">
      <div>
        <label class="block text-sm text-gray-600 mb-1">Название</label>
        <input type="text" name="name" id="edit-direction-name" required
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
      </div>
      <div>
        <label class="block text-sm text-gray-600 mb-1">Описание</label>
        <textarea name="description" id="edit-direction-description" rows="3"
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"></textarea>
      </div>
      <div class="flex items-center justify-end gap-2 pt-2">
        <button type="button" onclick="closeEditDirectionModal()"
          class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 rounded-lg">Отмена</button>
        <button type="submit" class="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg">Сохранить</button>
      </div>
    </form>
  </div>
</div>

<!-- Modal: Delete direction -->
<div id="delete-direction-modal" class="fixed inset-0 bg-black/50 z-50 hidden flex items-center justify-center p-4">
  <div class="bg-white rounded-2xl w-full max-w-md p-6 shadow-xl">
    <h3 class="text-lg font-semibold text-gray-800 mb-2">Удалить направление?</h3>
    <p class="text-sm text-gray-600 mb-4">Вы собираетесь удалить направление <span id="delete-direction-name" class="font-medium"></span>. Это необратимо.</p>

    <div class="bg-red-50 rounded-lg p-3 mb-4 text-sm text-red-700 space-y-1">
      <div id="delete-direction-slots">Слотов: <span>0</span></div>
      <div id="delete-direction-bookings">Броней: <span>0</span></div>
      <div id="delete-direction-leaders">Руководителей: <span>0</span></div>
      <div id="delete-direction-prefs">Предпочтений: <span>0</span></div>
    </div>

    <form method="post" id="delete-direction-form" class="flex items-center justify-end gap-2">
      <button type="button" onclick="closeDeleteDirectionModal()"
        class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 rounded-lg">Отмена</button>
      <button type="submit" class="px-4 py-2 text-sm bg-red-600 hover:bg-red-700 text-white rounded-lg">Удалить</button>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Add JS for modals**

```javascript
function openEditDirectionModal(id, name, description) {
  document.getElementById('edit-direction-id').value = id;
  document.getElementById('edit-direction-form').action = '/admin/direction/' + id + '/edit';
  document.getElementById('edit-direction-name').value = name;
  document.getElementById('edit-direction-description').value = description;
  document.getElementById('edit-direction-modal').classList.remove('hidden');
}
function closeEditDirectionModal() {
  document.getElementById('edit-direction-modal').classList.add('hidden');
}

function openDeleteDirectionModal(id, name) {
  document.getElementById('delete-direction-name').textContent = name;
  document.getElementById('delete-direction-form').action = '/admin/direction/' + id + '/delete';
  document.getElementById('delete-direction-modal').classList.remove('hidden');

  fetch('/admin/direction/' + id + '/delete-info')
    .then(r => r.json())
    .then(data => {
      document.querySelector('#delete-direction-slots span').textContent = data.slots_count;
      document.querySelector('#delete-direction-bookings span').textContent = data.bookings_count;
      document.querySelector('#delete-direction-leaders span').textContent = data.leaders_count;
      document.querySelector('#delete-direction-prefs span').textContent = data.prefs_count;
    });
}
function closeDeleteDirectionModal() {
  document.getElementById('delete-direction-modal').classList.add('hidden');
}
```

- [ ] **Step 6: Verify endpoints**

Run: `python -m pytest tests/test_admin_directions.py -v` (Task 7).
Expected: PASS

---

## Task 7: Write tests

**Files:**
- Create: `tests/test_admin_audit_logs.py`
- Create: `tests/test_admin_directions.py`
- Create: `tests/test_admin_filters_url.py`
- Create: `tests/test_admin_mobile_mass_actions.py`

- [ ] **Step 1: Audit log tests**

Create `tests/test_admin_audit_logs.py`:
```python
import pytest
import json

from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, ROLE_VOLUNTEER, COOKIE_NAME
import models


@pytest.fixture
def admin_with_session(db, client):
    admin = models.User(
        username="audit_admin",
        full_name="Audit Admin",
        password_hash=hash_password("adminpass"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.cookies.set(COOKIE_NAME, sign_cookie(admin.id))
    yield admin
    existing = db.query(models.User).filter_by(id=admin.id).first()
    if existing:
        db.delete(existing)
    db.commit()


@pytest.fixture
def sample_users(db, client):
    u1 = models.User(username="audit_vol1", full_name="Audit Vol 1", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=False)
    u2 = models.User(username="audit_vol2", full_name="Audit Vol 2", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=True)
    db.add_all([u1, u2])
    db.commit()
    for u in [u1, u2]:
        db.refresh(u)
    yield [u1, u2]
    for u in [u1, u2]:
        existing = db.query(models.User).filter_by(id=u.id).first()
        if existing:
            db.delete(existing)
    db.commit()


def test_mass_action_creates_audit_log(client, admin_with_session, sample_users, db):
    response = client.post("/admin/users/mass-action", data={
        "action": "activate",
        "user_ids": [u.id for u in sample_users],
    }, follow_redirects=False)
    assert response.status_code == 302

    log = db.query(models.AdminActionLog).order_by(models.AdminActionLog.id.desc()).first()
    assert log is not None
    assert log.action == "activate"
    assert log.admin_id == admin_with_session.id
    assert log.target_count == 2
    details = json.loads(log.details)
    assert len(details["user_ids"]) == 2


def test_audit_log_page_requires_admin(client, db):
    response = client.get("/admin/action-logs", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers.get("location") in ("/", "/login")


def test_audit_log_page_renders_for_admin(client, admin_with_session, db):
    response = client.get("/admin/action-logs")
    assert response.status_code == 200
    assert "История действий" in response.text
```

- [ ] **Step 2: Direction tests**

Create `tests/test_admin_directions.py`:
```python
import pytest
from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, COOKIE_NAME
import models


@pytest.fixture
def admin_with_session(db, client):
    admin = models.User(username="dir_admin", full_name="Dir Admin", password_hash=hash_password("adminpass"), role=ROLE_ADMIN, is_active=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.cookies.set(COOKIE_NAME, sign_cookie(admin.id))
    yield admin
    db.delete(admin)
    db.commit()


@pytest.fixture
def direction(db):
    d = models.Direction(name="Test Direction", description="Original")
    db.add(d)
    db.commit()
    db.refresh(d)
    yield d
    existing = db.query(models.Direction).filter_by(id=d.id).first()
    if existing:
        db.delete(existing)
    db.commit()


def test_edit_direction(client, admin_with_session, direction, db):
    response = client.post(f"/admin/direction/{direction.id}/edit", data={
        "name": "Updated Direction",
        "description": "New description",
    }, follow_redirects=False)
    assert response.status_code == 302
    db.refresh(direction)
    assert direction.name == "Updated Direction"
    assert direction.description == "New description"


def test_edit_direction_rejects_duplicate_name(client, admin_with_session, direction, db):
    other = models.Direction(name="Other Direction")
    db.add(other)
    db.commit()
    db.refresh(other)

    response = client.post(f"/admin/direction/{direction.id}/edit", data={
        "name": "Other Direction",
    }, follow_redirects=False)
    assert response.status_code == 302
    assert "toast_type=error" in (response.headers.get("location") or "")

    db.delete(other)
    db.commit()


def test_delete_direction_info(client, admin_with_session, direction, db):
    response = client.get(f"/admin/direction/{direction.id}/delete-info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == direction.name
    assert data["slots_count"] == 0


def test_delete_direction(client, admin_with_session, direction, db):
    direction_id = direction.id
    response = client.post(f"/admin/direction/{direction_id}/delete", follow_redirects=False)
    assert response.status_code == 302
    assert db.query(models.Direction).filter_by(id=direction_id).first() is None
```

- [ ] **Step 3: Filter URL sync test**

Create `tests/test_admin_filters_url.py`:
```python
import pytest
from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, COOKIE_NAME
import models


@pytest.fixture
def admin_with_session(db, client):
    admin = models.User(username="filter_admin", full_name="Filter Admin", password_hash=hash_password("adminpass"), role=ROLE_ADMIN, is_active=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.cookies.set(COOKIE_NAME, sign_cookie(admin.id))
    yield admin
    db.delete(admin)
    db.commit()


def test_admin_page_preserves_filter_params(client, admin_with_session):
    response = client.get("/admin?q=ivan&role=volunteer&status=active&direction=1&sort=name_asc")
    assert response.status_code == 200
    html = response.text
    assert 'value="ivan"' in html or 'value="Иван"' in html or "user-search" in html
    assert "filter-role" in html
```

- [ ] **Step 4: Mobile mass-action markup test**

Create `tests/test_admin_mobile_mass_actions.py`:
```python
import pytest
from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, COOKIE_NAME
import models


@pytest.fixture
def admin_with_session(db, client):
    admin = models.User(username="mobile_admin", full_name="Mobile Admin", password_hash=hash_password("adminpass"), role=ROLE_ADMIN, is_active=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.cookies.set(COOKIE_NAME, sign_cookie(admin.id))
    yield admin
    db.delete(admin)
    db.commit()


def test_admin_page_has_mobile_mass_action_markup(client, admin_with_session):
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.text
    assert "mobile-select-all" in html
    assert "mobile-user-checkbox" in html
    assert "mobile-mass-actions" in html
    assert "mobile-mass-new-role" in html
    assert "mobile-mass-direction" in html
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -q`
Expected: all pass

---

## Task 8: Final regression

**Files:** None

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 2: Verify migrations apply cleanly**

Run:
```bash
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
```
Expected: success

- [ ] **Step 3: Manual smoke checks**

Open `/admin` and verify:
- Mobile bottom bar appears when mobile checkbox checked
- URL updates when filters change
- Direction edit modal opens and saves
- Direction delete modal shows impact counts
- Action logs page accessible from sidebar

---

## Self-Review

**1. Spec coverage:**
- Mobile mass actions → Task 4
- Audit log model/migration → Task 1
- Audit log write → Task 2
- Action logs page → Task 3
- URL filter sync → Task 5
- Direction management → Task 6
- Tests → Task 7

**2. Placeholder scan:** None.

**3. Type consistency:**
- `AdminActionLog.details` stores JSON string
- `direction_id` in forms is string, parsed as int by FastAPI
- `page` is int

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-15-admin-improvements-v2.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach do you prefer?
