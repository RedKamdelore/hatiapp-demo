# Admin Search, Filters & Mass Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client-side filters (role, status, direction) and three new bulk operations (change role, add to direction, remove from direction) to the admin panel.

**Architecture:** Backend extends the existing `POST /admin/users/mass-action` form handler in `routers/admin.py` to process new action types. Frontend adds filter dropdowns and secondary-value selectors to `templates/admin.html`, storing per-row filter data in `data-*` attributes and using existing hidden-form JavaScript pattern.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy, SQLite, Tailwind-like utility classes, vanilla JS.

---

## File Structure

- `routers/admin.py` — extend `/admin/users/mass-action` with `change_role`, `add_to_direction`, `remove_from_direction`
- `templates/admin.html` — add filter controls, mass-action selectors, row/card `data-*` attributes, filter JS
- `tests/test_admin_mass_actions.py` — new test module covering mass actions and permission rules

---

## Task 1: Add filter data attributes to user rows and cards

**Files:**
- Modify: `templates/admin.html`

- [ ] **Step 1: Build per-row direction ID list in Jinja**

In the desktop table loop and mobile card loop, compute:
```jinja2
{% set user_dir_ids = [] %}
{% if u.role == 'leader' %}
  {% for dl in u.led_directions %}{% set _ = user_dir_ids.append(dl.direction_id) %}{% endfor %}
{% elif u.role == 'volunteer' %}
  {% for p in u.preferences %}{% set _ = user_dir_ids.append(p.direction_id) %}{% endfor %}
  {% for b in u.bookings %}{% if b.slot and b.slot.direction_id not in user_dir_ids %}{% set _ = user_dir_ids.append(b.slot.direction_id) %}{% endif %}{% endfor %}
{% endif %}
{% set dir_attr = user_dir_ids | join(',') %}
```

- [ ] **Step 2: Add `data-*` attributes to `.user-row` and `.mobile-user-card`**

Change the opening tags to include:
```html
<tr class="user-row ..." data-role="{{ u.role }}" data-status="{{ 'active' if u.is_active else 'blocked' }}" data-directions="{{ dir_attr }}" data-search="...">
```
and similarly for mobile cards.

- [ ] **Step 3: Verify in browser / tests that attributes are present**

Open `/admin` and inspect one row.

---

## Task 2: Add filter controls to the panel header

**Files:**
- Modify: `templates/admin.html`

- [ ] **Step 1: Replace the search-only header with filters**

Locate:
```html
<div class="search-box" style="width: 240px;">
  ...
  <input type="text" id="user-search" placeholder="Поиск по имени или логину..." oninput="filterUsers(this.value)"/>
</div>
```

Wrap in a flex container:
```html
<div class="flex items-center gap-2 flex-wrap">
  <div class="search-box" style="width: 200px;">...search input...</div>
  <select id="filter-role" onchange="applyFilters()" class="...">
    <option value="">Все роли</option>
    <option value="admin">Админ</option>
    <option value="leader">Руководитель</option>
    <option value="lotos">Лотос</option>
    <option value="volunteer">Волонтёр</option>
    <option value="permanent">Бессменный</option>
  </select>
  <select id="filter-status" onchange="applyFilters()" class="...">
    <option value="">Все статусы</option>
    <option value="active">Активные</option>
    <option value="blocked">Заблокированные</option>
  </select>
  <select id="filter-direction" onchange="applyFilters()" class="...">
    <option value="">Все направления</option>
    {% for d in directions %}
    <option value="{{ d.id }}">{{ d.name }}</option>
    {% endfor %}
  </select>
</div>
```

Note: `directions` variable is not currently passed to the template. It will be added in Task 4.

- [ ] **Step 2: Add reusable select styling**

Use existing Tailwind classes, e.g.:
```html
class="border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
```

- [ ] **Step 3: Replace `filterUsers` with `applyFilters`**

Update JS to combine search + filters:
```javascript
function applyFilters() {
  const q = document.getElementById('user-search').value.trim().toLowerCase();
  const role = document.getElementById('filter-role').value;
  const status = document.getElementById('filter-status').value;
  const direction = document.getElementById('filter-direction').value;

  const rows = document.querySelectorAll('.user-row');
  let visible = 0;
  rows.forEach(function(row) {
    const text = row.dataset.search || '';
    const rowRole = row.dataset.role || '';
    const rowStatus = row.dataset.status || '';
    const rowDirs = (row.dataset.directions || '').split(',').filter(Boolean);

    const matchesSearch = !q || text.includes(q);
    const matchesRole = !role || rowRole === role;
    const matchesStatus = !status || rowStatus === status;
    const matchesDirection = !direction || rowDirs.includes(direction);

    const show = matchesSearch && matchesRole && matchesStatus && matchesDirection;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });

  const cards = document.querySelectorAll('.mobile-user-card');
  cards.forEach(function(card) {
    const text = card.dataset.search || '';
    const rowRole = card.dataset.role || '';
    const rowStatus = card.dataset.status || '';
    const rowDirs = (card.dataset.directions || '').split(',').filter(Boolean);

    const show = (!q || text.includes(q))
      && (!role || rowRole === role)
      && (!status || rowStatus === status)
      && (!direction || rowDirs.includes(direction));
    card.style.display = show ? '' : 'none';
  });

  const noDesk = document.getElementById('no-users');
  if (noDesk) noDesk.classList.toggle('hidden', visible > 0);
  updateCountLabel(visible);
}
```

Change `oninput` to call `applyFilters()`.

- [ ] **Step 4: Refresh and verify filters work**

Open `/admin`, select a role, only matching rows should remain.

---

## Task 3: Add backend endpoint changes for new mass actions

**Files:**
- Modify: `routers/admin.py`

- [ ] **Step 1: Update `/admin` route to pass directions to template**

Find the `admin_panel` function and ensure `directions` query is executed and passed:
```python
directions = db.query(models.Direction).order_by(models.Direction.name).all()
```

Add to the `TemplateResponse` context:
```python
"directions": directions,
```

- [ ] **Step 2: Extend `mass_action_users` signature**

Change:
```python
def mass_action_users(
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),
    user_ids: list[int] = Form(default=[]),
):
```

to:
```python
def mass_action_users(
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),
    user_ids: list[int] = Form(default=[]),
    new_role: str = Form(""),
    direction_id: int = Form(None),
):
```

- [ ] **Step 3: Add helper to add/remove direction links**

Inside `mass_action_users`, before the loop, add:
```python
ALLOWED_MASS_ROLES = (ROLE_LEADER, ROLE_LOTOS, ROLE_VOLUNTEER, ROLE_PERMANENT)
```

Add to the loop after existing actions:
```python
elif action == "change_role":
    if u.role != ROLE_ADMIN and new_role in ALLOWED_MASS_ROLES:
        u.role = new_role
        count += 1
elif action == "add_to_direction":
    if direction_id and u.role == ROLE_LEADER:
        exists = db.query(models.DirectionLeader).filter_by(
            direction_id=direction_id, user_id=u.id
        ).first()
        if not exists:
            db.add(models.DirectionLeader(direction_id=direction_id, user_id=u.id))
            count += 1
    elif direction_id and u.role == ROLE_VOLUNTEER:
        exists = db.query(models.UserPreference).filter_by(
            direction_id=direction_id, user_id=u.id
        ).first()
        if not exists:
            db.add(models.UserPreference(direction_id=direction_id, user_id=u.id))
            count += 1
elif action == "remove_from_direction":
    if direction_id and u.role == ROLE_LEADER:
        link = db.query(models.DirectionLeader).filter_by(
            direction_id=direction_id, user_id=u.id
        ).first()
        if link:
            db.delete(link)
            count += 1
    elif direction_id and u.role == ROLE_VOLUNTEER:
        link = db.query(models.UserPreference).filter_by(
            direction_id=direction_id, user_id=u.id
        ).first()
        if link:
            db.delete(link)
            count += 1
```

- [ ] **Step 4: Run existing tests**

Run: `pytest tests/ -q`
Expected: all pass

---

## Task 4: Add new mass-action UI controls

**Files:**
- Modify: `templates/admin.html`

- [ ] **Step 1: Add secondary-value selects and action buttons**

In the mass-actions bar (`#mass-actions`), add after existing buttons:
```html
<div class="h-4 w-px bg-gray-200 mx-1"></div>
<select id="mass-new-role" class="...">
  <option value="" disabled selected>Новая роль</option>
  <option value="leader">Руководитель</option>
  <option value="lotos">Лотос</option>
  <option value="volunteer">Волонтёр</option>
  <option value="permanent">Бессменный</option>
</select>
<button type="button" data-action="change_role" class="mass-btn ...">📝 Сменить роль</button>

<select id="mass-direction" class="...">
  <option value="" disabled selected>Направление</option>
  {% for d in directions %}
  <option value="{{ d.id }}">{{ d.name }}</option>
  {% endfor %}
</select>
<button type="button" data-action="add_to_direction" class="mass-btn ...">➕ Назначить</button>
<button type="button" data-action="remove_from_direction" class="mass-btn ...">➖ Убрать</button>
```

- [ ] **Step 2: Update mass-action JS to read secondary values**

Inside the `.mass-btn` click handler, replace the simple submit with:
```javascript
const action = btn.dataset.action;
let extraName = null;
let extraValue = null;
let extraInput = null;

if (action === 'change_role') {
  const select = document.getElementById('mass-new-role');
  if (!select.value) { alert('Выберите роль'); return; }
  extraName = 'new_role';
  extraValue = select.value;
} else if (action === 'add_to_direction' || action === 'remove_from_direction') {
  const select = document.getElementById('mass-direction');
  if (!select.value) { alert('Выберите направление'); return; }
  extraName = 'direction_id';
  extraValue = select.value;
}

if (action === 'delete' && !confirm('Удалить выбранных пользователей?')) return;

hiddenForm.querySelectorAll('input[name="user_ids"]').forEach(el => el.remove());
hiddenForm.querySelectorAll('input[name="new_role"]').forEach(el => el.remove());
hiddenForm.querySelectorAll('input[name="direction_id"]').forEach(el => el.remove());

checked.forEach(function(cb) {
  const input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'user_ids';
  input.value = cb.value;
  hiddenForm.appendChild(input);
});

if (extraName) {
  extraInput = document.createElement('input');
  extraInput.type = 'hidden';
  extraInput.name = extraName;
  extraInput.value = extraValue;
  hiddenForm.appendChild(extraInput);
}

actionInput.value = action;
hiddenForm.submit();
```

- [ ] **Step 3: Verify in browser**

Select users, choose "Сменить роль" → reloads with success toast and updated roles.

---

## Task 5: Write tests for mass actions

**Files:**
- Create: `tests/test_admin_mass_actions.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from database import get_db
from services.auth import hash_password
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_VOLUNTEER, ROLE_LOTOS
import models

TEST_DATABASE_URL = "sqlite:///./test.db"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_with_session(client):
    """Create admin and login session."""
    db = TestingSessionLocal()
    admin = models.User(
        username="massadmin",
        full_name="Mass Admin",
        password_hash=hash_password("adminpass"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.post("/login", data={"username": "massadmin", "password": "adminpass"})
    yield admin
    db.delete(admin)
    db.commit()
    db.close()


@pytest.fixture
def sample_users(client):
    db = TestingSessionLocal()
    u1 = models.User(username="vol1", full_name="Vol 1", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=False)
    u2 = models.User(username="vol2", full_name="Vol 2", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=True)
    u3 = models.User(username="lead1", full_name="Lead 1", password_hash=hash_password("p"), role=ROLE_LEADER, is_active=True)
    db.add_all([u1, u2, u3])
    db.commit()
    for u in [u1, u2, u3]:
        db.refresh(u)
    yield [u1, u2, u3]
    for u in [u1, u2, u3]:
        db.delete(u)
    db.commit()
    db.close()


@pytest.fixture
def direction():
    db = TestingSessionLocal()
    d = models.Direction(name="Mass Direction")
    db.add(d)
    db.commit()
    db.refresh(d)
    yield d
    db.delete(d)
    db.commit()
    db.close()


def test_mass_activate(client, admin_with_session, sample_users):
    ids = [u.id for u in sample_users[:2]]
    response = client.post("/admin/users/mass-action", data={
        "action": "activate",
        "user_ids": ids,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    assert db.query(models.User).filter_by(id=sample_users[0].id).first().is_active is True
    db.close()


def test_mass_deactivate_skips_admin(client, admin_with_session, sample_users):
    ids = [admin_with_session.id, sample_users[0].id]
    response = client.post("/admin/users/mass-action", data={
        "action": "deactivate",
        "user_ids": ids,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    assert db.query(models.User).filter_by(id=admin_with_session.id).first().is_active is True
    assert db.query(models.User).filter_by(id=sample_users[0].id).first().is_active is False
    db.close()


def test_mass_delete_skips_admin(client, admin_with_session, sample_users):
    ids = [admin_with_session.id, sample_users[0].id]
    response = client.post("/admin/users/mass-action", data={
        "action": "delete",
        "user_ids": ids,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    assert db.query(models.User).filter_by(id=admin_with_session.id).first() is not None
    assert db.query(models.User).filter_by(id=sample_users[0].id).first() is None
    db.close()


def test_mass_change_role_excludes_admin_target(client, admin_with_session, sample_users):
    ids = [admin_with_session.id, sample_users[0].id]
    response = client.post("/admin/users/mass-action", data={
        "action": "change_role",
        "user_ids": ids,
        "new_role": ROLE_LOTOS,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    assert db.query(models.User).filter_by(id=admin_with_session.id).first().role == ROLE_ADMIN
    assert db.query(models.User).filter_by(id=sample_users[0].id).first().role == ROLE_LOTOS
    db.close()


def test_mass_add_to_direction_leader(client, admin_with_session, sample_users, direction):
    leader = [u for u in sample_users if u.role == ROLE_LEADER][0]
    response = client.post("/admin/users/mass-action", data={
        "action": "add_to_direction",
        "user_ids": [leader.id],
        "direction_id": direction.id,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    link = db.query(models.DirectionLeader).filter_by(user_id=leader.id, direction_id=direction.id).first()
    assert link is not None
    db.close()


def test_mass_add_to_direction_volunteer(client, admin_with_session, sample_users, direction):
    volunteer = [u for u in sample_users if u.role == ROLE_VOLUNTEER][0]
    response = client.post("/admin/users/mass-action", data={
        "action": "add_to_direction",
        "user_ids": [volunteer.id],
        "direction_id": direction.id,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    pref = db.query(models.UserPreference).filter_by(user_id=volunteer.id, direction_id=direction.id).first()
    assert pref is not None
    db.close()


def test_mass_remove_from_direction_leader(client, admin_with_session, sample_users, direction):
    db = TestingSessionLocal()
    leader = [u for u in sample_users if u.role == ROLE_LEADER][0]
    db.add(models.DirectionLeader(user_id=leader.id, direction_id=direction.id))
    db.commit()
    db.close()

    response = client.post("/admin/users/mass-action", data={
        "action": "remove_from_direction",
        "user_ids": [leader.id],
        "direction_id": direction.id,
    }, follow_redirects=False)
    assert response.status_code == 302
    db = TestingSessionLocal()
    link = db.query(models.DirectionLeader).filter_by(user_id=leader.id, direction_id=direction.id).first()
    assert link is None
    db.close()
```

- [ ] **Step 2: Run tests and fix failures**

Run: `pytest tests/test_admin_mass_actions.py -v`
Expected: PASS

---

## Task 6: Regression test the full suite

**Files:**
- None

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -q`
Expected: all pass

- [ ] **Step 2: Smoke-test admin page HTML**

Run: `python -c "from fastapi.testclient import TestClient; from main import app; c=TestClient(app); ..."`
Or simply verify that `/admin` returns 200 and contains filter selects.

- [ ] **Step 3: Commit**

```bash
git add routers/admin.py templates/admin.html tests/test_admin_mass_actions.py docs/superpowers/specs/2026-06-15-admin-search-filters-mass-actions.md docs/superpowers/plans/2026-06-15-admin-search-filters-mass-actions.md
git commit -m "feat(admin): filters by role/status/direction and bulk role/direction actions"
```

---

## Self-Review

**1. Spec coverage:**
- Role filter → Task 2
- Status filter → Task 2
- Direction filter → Tasks 1–2
- Change role mass action → Tasks 3–4
- Add/remove direction mass action → Tasks 3–4
- Admin protection → Task 3 and tests
- Mobile cards → Task 1–2

**2. Placeholder scan:** None.

**3. Type consistency:**
- `direction_id` is passed as string in JS, parsed by FastAPI as `int`
- `new_role` passed as string, validated against `ALLOWED_MASS_ROLES`

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-15-admin-search-filters-mass-actions.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach do you prefer?
