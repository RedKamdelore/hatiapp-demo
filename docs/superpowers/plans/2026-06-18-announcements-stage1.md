# Announcements Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public announcements feed with separate post pages, attachments, pinning, and notifications.

**Architecture:** Add `Announcement` and `AnnouncementAttachment` models, expose REST endpoints under `/api/announcements`, render feed and single-post templates, and broadcast SSE events on new posts. Attachments are stored on disk under `static/uploads/announcements/`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Jinja2, vanilla JS, SSE via `services/sse_manager.py`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `models.py` | `Announcement`, `AnnouncementAttachment` models |
| `alembic/versions/2026_06_18_announcements.py` | Migration for new tables |
| `routers/announcements.py` | All announcement API routes |
| `templates/announcements.html` | Feed page |
| `templates/announcement.html` | Single post page |
| `templates/base.html` | Bottom nav tab + SSE handler |
| `static/sw.js` | Push/foreground handler for `announcement` events |
| `tests/test_announcements.py` | API and template tests |
| `main.py` | Register `announcements` router |

---

### Task 1: Database Models

**Files:**
- Modify: `models.py:1-214`

- [ ] **Step 1: Add `Announcement` and `AnnouncementAttachment` models**

Append to `models.py`:

```python
class Announcement(Base):
    __tablename__ = "announcements"

    id          = Column(Integer, primary_key=True)
    author_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title       = Column(String, nullable=True)
    content     = Column(Text, nullable=False)
    is_pinned   = Column(Boolean, default=False, index=True)
    created_at  = Column(DateTime, server_default=func.now(), index=True)
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    author = relationship("User")
    attachments = relationship("AnnouncementAttachment", cascade="all, delete", order_by="AnnouncementAttachment.id")


class AnnouncementAttachment(Base):
    __tablename__ = "announcement_attachments"

    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    file_path       = Column(String, nullable=False)
    file_type       = Column(String, nullable=False)
    created_at      = Column(DateTime, server_default=func.now())
```

- [ ] **Step 2: Update `User` relationships**

Add to `User` class:

```python
announcements = relationship("Announcement", back_populates="author", cascade="all, delete")
```

And update `Announcement`:

```python
author = relationship("User", back_populates="announcements")
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `alembic/versions/2026_06_18_add_announcements.py`

- [ ] **Step 1: Generate migration**

Run:

```bash
alembic revision --autogenerate -m "add announcements"
```

- [ ] **Step 2: Verify migration contains both tables and indexes**

Expected tables: `announcements`, `announcement_attachments`.

- [ ] **Step 3: Apply migration**

Run:

```bash
alembic upgrade head
```

---

### Task 3: Announcements Router

**Files:**
- Create: `routers/announcements.py`

- [ ] **Step 1: Write router scaffold**

```python
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
import uuid
import mimetypes
from pathlib import Path
import shutil

import models
from database import get_db
from services.auth import get_current_user, require_role
from services.sse_manager import sse_manager
from config import BASE_DIR

router = APIRouter(prefix="/api/announcements", tags=["announcements"])

UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "announcements"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024

ALLOWED_TYPES = IMAGE_TYPES | VIDEO_TYPES


def can_moderate(user: models.User, post: models.Announcement) -> bool:
    if user.id == post.author_id:
        return True
    return user.role in {"admin", "lotos", "leader"}


def can_pin(user: models.User) -> bool:
    return user.role in {"admin", "lotos", "leader"}


def serialize_post(post: models.Announcement) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "is_pinned": post.is_pinned,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "author": {
            "id": post.author.id,
            "username": post.author.username,
            "full_name": post.author.full_name,
            "avatar": post.author.avatar,
        },
        "attachments": [
            {"id": a.id, "url": a.file_path, "type": a.file_type}
            for a in post.attachments
        ],
    }
```

- [ ] **Step 2: Add create endpoint**

```python
@router.post("")
async def create_announcement(
    request: Request,
    title: Optional[str] = Form(None),
    content: str = Form(...),
    is_pinned: bool = Form(False),
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)

    if is_pinned and not can_pin(user):
        raise HTTPException(status_code=403, detail="Нет прав для закрепления")

    if is_pinned:
        pinned_count = db.query(models.Announcement).filter_by(is_pinned=True).count()
        if pinned_count >= 3:
            raise HTTPException(status_code=400, detail="Максимум 3 закреплённых поста")

    post = models.Announcement(
        author_id=user.id,
        title=title.strip() if title else None,
        content=content.strip(),
        is_pinned=is_pinned,
    )
    db.add(post)
    db.flush()

    for file in files:
        if not file.filename:
            continue
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {content_type}")

        file_bytes = await file.read()
        if content_type in IMAGE_TYPES and len(file_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Изображение слишком большое (максимум 100 МБ)")
        if content_type in VIDEO_TYPES and len(file_bytes) > MAX_VIDEO_BYTES:
            raise HTTPException(status_code=400, detail="Видео слишком большое (максимум 2 ГБ)")

        ext = Path(file.filename).suffix.lower() or ".bin"
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        attachment = models.AnnouncementAttachment(
            announcement_id=post.id,
            file_path=f"/static/uploads/announcements/{filename}",
            file_type="image" if content_type in IMAGE_TYPES else "video",
        )
        db.add(attachment)

    db.commit()
    db.refresh(post)

    await sse_manager.broadcast({
        "type": "announcement",
        "post_id": post.id,
        "title": post.title,
        "author_name": post.author.full_name or post.author.username,
    })

    return serialize_post(post)
```

- [ ] **Step 3: Add list endpoint**

```python
@router.get("")
def list_announcements(
    request: Request,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    get_current_user(request, db)
    pinned = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.author), joinedload(models.Announcement.attachments))
        .filter_by(is_pinned=True)
        .order_by(models.Announcement.created_at.desc())
        .all()
    )
    regular = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.author), joinedload(models.Announcement.attachments))
        .filter_by(is_pinned=False)
        .order_by(models.Announcement.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return {
        "pinned": [serialize_post(p) for p in pinned],
        "posts": [serialize_post(p) for p in regular],
        "limit": limit,
        "offset": offset,
    }
```

- [ ] **Step 4: Add single post endpoint**

```python
@router.get("/{post_id}")
def get_announcement(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    get_current_user(request, db)
    post = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.author), joinedload(models.Announcement.attachments))
        .filter_by(id=post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    return serialize_post(post)
```

- [ ] **Step 5: Add update endpoint**

```python
@router.put("/{post_id}")
async def update_announcement(
    request: Request,
    post_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    is_pinned: Optional[bool] = Form(None),
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    if not can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")

    if content is not None:
        post.content = content.strip()
    if title is not None:
        post.title = title.strip() or None

    if is_pinned is not None and is_pinned != post.is_pinned:
        if not can_pin(user):
            raise HTTPException(status_code=403, detail="Нет прав для закрепления")
        if is_pinned:
            pinned_count = db.query(models.Announcement).filter_by(is_pinned=True).count()
            if pinned_count >= 3:
                raise HTTPException(status_code=400, detail="Максимум 3 закреплённых поста")
        post.is_pinned = is_pinned

    post.updated_at = datetime.utcnow()

    for file in files:
        if not file.filename:
            continue
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {content_type}")
        file_bytes = await file.read()
        if content_type in IMAGE_TYPES and len(file_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Изображение слишком большое")
        if content_type in VIDEO_TYPES and len(file_bytes) > MAX_VIDEO_BYTES:
            raise HTTPException(status_code=400, detail="Видео слишком большое")

        ext = Path(file.filename).suffix.lower() or ".bin"
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        attachment = models.AnnouncementAttachment(
            announcement_id=post.id,
            file_path=f"/static/uploads/announcements/{filename}",
            file_type="image" if content_type in IMAGE_TYPES else "video",
        )
        db.add(attachment)

    db.commit()
    db.refresh(post)
    return serialize_post(post)
```

- [ ] **Step 6: Add delete endpoint**

```python
@router.delete("/{post_id}")
def delete_announcement(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.attachments))
        .filter_by(id=post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    if not can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")

    for attachment in post.attachments:
        try:
            (BASE_DIR / attachment.file_path.lstrip("/")).unlink(missing_ok=True)
        except Exception:
            pass

    db.delete(post)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 7: Add pin endpoint**

```python
@router.post("/{post_id}/pin")
def pin_announcement(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not can_pin(user):
        raise HTTPException(status_code=403, detail="Нет прав")

    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")

    new_state = not post.is_pinned
    if new_state:
        pinned_count = db.query(models.Announcement).filter_by(is_pinned=True).count()
        if pinned_count >= 3:
            raise HTTPException(status_code=400, detail="Максимум 3 закреплённых поста")

    post.is_pinned = new_state
    post.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    return serialize_post(post)
```

- [ ] **Step 8: Add HTML page routes**

Append to same file or create separate page routes. For simplicity keep in same router:

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")


@router.get("/announcements", response_class=HTMLResponse)
def announcements_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("announcements.html", {"request": request, "user": user})


@router.get("/a/{post_id}", response_class=HTMLResponse)
def announcement_page(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.author), joinedload(models.Announcement.attachments))
        .filter_by(id=post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    return templates.TemplateResponse("announcement.html", {
        "request": request,
        "user": user,
        "post": post,
        "can_edit": can_moderate(user, post),
        "can_pin": can_pin(user),
    })
```

Note: prefix conflict. Since router prefix is `/api/announcements`, page routes must live on a separate non-prefixed router. Create `routers/pages.py` or add page routes directly in `main.py`. Recommended: add page routes to a new `APIRouter()` without prefix in `routers/announcements.py` and include both in `main.py`.

---

### Task 4: Register Router in main.py

**Files:**
- Modify: `main.py:18`

- [ ] **Step 1: Import and include router**

Change import line:

```python
from routers import auth, schedule, leader, admin, profile, chat, sse, logs, slots, announcements
```

Add:

```python
app.include_router(announcements.router)
app.include_router(announcements.api_router)
```

Modify `routers/announcements.py` to expose:

```python
router = APIRouter(tags=["announcements"])  # pages: /announcements, /a/{id}
api_router = APIRouter(prefix="/api/announcements", tags=["announcements"])  # API
```

Move all `/api/...` endpoints to `api_router` and page routes to `router`.

---

### Task 5: Feed Template

**Files:**
- Create: `templates/announcements.html`

- [ ] **Step 1: Create feed page**

```html
{% extends "base.html" %}
{% block title %}Объявления{% endblock %}
{% block content %}
<div class="space-y-4" id="feed">
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Объявления</h1>
    <button onclick="openCreateModal()" class="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium">Новый пост</button>
  </div>

  <div id="pinned-list" class="space-y-3"></div>
  <div id="posts-list" class="space-y-3"></div>

  <button id="load-more" onclick="loadMore()" class="w-full py-3 text-indigo-600 font-medium hidden">Загрузить ещё</button>
</div>

<!-- Create Modal -->
<div id="create-modal" class="fixed inset-0 bg-black/50 z-50 hidden flex items-end sm:items-center justify-center p-0 sm:p-4">
  <div class="bg-white dark:bg-[#1e1e1e] w-full max-w-2xl rounded-t-2xl sm:rounded-2xl p-4 space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-bold">Новое объявление</h2>
      <button onclick="closeCreateModal()" class="text-gray-500">✕</button>
    </div>
    <form id="create-form" class="space-y-3" enctype="multipart/form-data">
      <input type="text" name="title" placeholder="Заголовок (необязательно)" class="w-full border rounded-lg px-3 py-2 dark:bg-[#181818]"/>
      <textarea name="content" rows="4" placeholder="Текст объявления" required class="w-full border rounded-lg px-3 py-2 dark:bg-[#181818]"></textarea>
      <input type="file" name="files" multiple accept="image/*,video/*" class="w-full text-sm"/>
      {% if can_pin %}
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" name="is_pinned" value="true"/> Закрепить
      </label>
      {% endif %}
      <button type="submit" class="w-full bg-indigo-600 text-white py-2 rounded-lg font-medium">Опубликовать</button>
    </form>
  </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script>
let offset = 0;
let limit = 10;
let canPin = {{ 'true' if can_pin else 'false' }};

async function loadFeed(reset=false) {
  if (reset) {
    document.getElementById('pinned-list').innerHTML = '';
    document.getElementById('posts-list').innerHTML = '';
    offset = 0;
  }
  const res = await fetch(`/api/announcements?limit=${limit}&offset=${offset}`);
  const data = await res.json();
  renderPosts(data.pinned, 'pinned-list', true);
  if (offset === 0) document.getElementById('posts-list').innerHTML = '';
  renderPosts(data.posts, 'posts-list', false);
  offset += data.posts.length;
  document.getElementById('load-more').classList.toggle('hidden', data.posts.length < limit);
}

function renderPosts(posts, containerId, isPinned) {
  const container = document.getElementById(containerId);
  posts.forEach(post => {
    const card = document.createElement('a');
    card.href = `/a/${post.id}`;
    card.className = 'block bg-white dark:bg-[#1e1e1e] rounded-xl p-4 shadow-sm border border-gray-100 dark:border-[#2e2e2e]';
    const title = post.title ? `<h3 class="font-bold text-lg mb-1">${escapeHtml(post.title)}</h3>` : '';
    const text = `<p class="text-gray-600 dark:text-gray-400 text-sm line-clamp-3">${escapeHtml(post.content)}</p>`;
    const meta = `<div class="text-xs text-gray-400 mt-2">${escapeHtml(post.author.full_name || post.author.username)} · ${formatDate(post.created_at)} ${post.attachments.length ? '· 📎' : ''}</div>`;
    const pin = isPinned ? '<span class="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded">Закреплено</span>' : '';
    card.innerHTML = pin + title + text + meta;
    container.appendChild(card);
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' });
}

function loadMore() {
  loadFeed();
}

function openCreateModal() {
  document.getElementById('create-modal').classList.remove('hidden');
}
function closeCreateModal() {
  document.getElementById('create-modal').classList.add('hidden');
}

document.getElementById('create-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const formData = new FormData(this);
  const res = await fetch('/api/announcements', { method: 'POST', body: formData });
  if (res.ok) {
    closeCreateModal();
    this.reset();
    loadFeed(true);
  } else {
    const err = await res.json();
    showToast(err.detail || 'Ошибка', 'error');
  }
});

loadFeed(true);
</script>
{% endblock %}
```

Note: `can_pin` must be passed from backend route or inferred from user role. Pass `can_pin = user.role in ('admin','lotos','leader')` in `announcements_page`.

---

### Task 6: Single Post Template

**Files:**
- Create: `templates/announcement.html`

- [ ] **Step 1: Create post page**

```html
{% extends "base.html" %}
{% block title %}{{ post.title or 'Объявление' }}{% endblock %}
{% block content %}
<div class="bg-white dark:bg-[#1e1e1e] rounded-xl p-4 shadow-sm border border-gray-100 dark:border-[#2e2e2e] space-y-4" id="post-card">
  <div class="flex items-start justify-between">
    <div>
      <div class="text-sm text-gray-500">{{ post.author.full_name or post.author.username }}</div>
      <div class="text-xs text-gray-400">{{ post.created_at.strftime('%d %b %Y %H:%M') }}</div>
    </div>
    <div class="flex gap-2">
      {% if can_pin %}
      <button onclick="togglePin()" class="text-sm text-indigo-600">{{ 'Открепить' if post.is_pinned else 'Закрепить' }}</button>
      {% endif %}
      {% if can_edit %}
      <button onclick="startEdit()" class="text-sm text-gray-600">Редактировать</button>
      <button onclick="deletePost()" class="text-sm text-red-600">Удалить</button>
      {% endif %}
    </div>
  </div>

  <div id="view-mode">
    {% if post.title %}<h1 class="text-xl font-bold">{{ post.title }}</h1>{% endif %}
    <div class="text-gray-800 dark:text-gray-200 whitespace-pre-wrap">{{ post.content }}</div>
  </div>

  <form id="edit-form" class="hidden space-y-3" enctype="multipart/form-data">
    <input type="text" name="title" id="edit-title" value="{{ post.title or '' }}" class="w-full border rounded-lg px-3 py-2 dark:bg-[#181818]"/>
    <textarea name="content" id="edit-content" rows="6" required class="w-full border rounded-lg px-3 py-2 dark:bg-[#181818]">{{ post.content }}</textarea>
    <input type="file" name="files" multiple accept="image/*,video/*" class="w-full text-sm"/>
    <div class="flex gap-2">
      <button type="submit" class="bg-indigo-600 text-white px-4 py-2 rounded-lg">Сохранить</button>
      <button type="button" onclick="cancelEdit()" class="px-4 py-2 rounded-lg border">Отмена</button>
    </div>
  </form>

  {% if post.attachments %}
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
    {% for a in post.attachments %}
      {% if a.file_type == 'image' %}
      <img src="{{ a.file_path }}" class="rounded-lg max-h-96 object-cover w-full"/>
      {% else %}
      <video src="{{ a.file_path }}" controls class="rounded-lg w-full"></video>
      {% endif %}
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endblock %}

{% block extra_scripts %}
<script>
const postId = {{ post.id }};

function startEdit() {
  document.getElementById('view-mode').classList.add('hidden');
  document.getElementById('edit-form').classList.remove('hidden');
}
function cancelEdit() {
  document.getElementById('view-mode').classList.remove('hidden');
  document.getElementById('edit-form').classList.add('hidden');
}

document.getElementById('edit-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const formData = new FormData(this);
  const res = await fetch(`/api/announcements/${postId}`, { method: 'PUT', body: formData });
  if (res.ok) {
    location.reload();
  } else {
    const err = await res.json();
    showToast(err.detail || 'Ошибка', 'error');
  }
});

async function deletePost() {
  if (!confirm('Удалить объявление?')) return;
  const res = await fetch(`/api/announcements/${postId}`, { method: 'DELETE' });
  if (res.ok) {
    location.href = '/announcements';
  } else {
    showToast('Ошибка удаления', 'error');
  }
}

async function togglePin() {
  const res = await fetch(`/api/announcements/${postId}/pin`, { method: 'POST' });
  if (res.ok) {
    location.reload();
  } else {
    const err = await res.json();
    showToast(err.detail || 'Ошибка', 'error');
  }
}
</script>
{% endblock %}
```

---

### Task 7: Navigation Tab

**Files:**
- Modify: `templates/base.html:289-296`

- [ ] **Step 1: Add announcements tab after chat**

Insert before chat link or after profile. Insert after profile for visibility:

```html
<!-- Объявления — у всех -->
<a href="/announcements" class="nav-item {% if request.url.path == '/announcements' or request.url.path.startswith('/a/') %}active{% endif %}" style="position:relative">
  <svg viewBox="0 0 24 24" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M10.34 15.84c-.688-.06-1.386-.09-2.09-.09H7.5a4.5 4.5 0 110-9h.75c.704 0 1.402-.03 2.09-.09m0 9.18c.253.962.584 1.892.985 2.783.247.55.06 1.21-.463 1.511l-.657.38c-.551.318-1.26.117-1.527-.461a20.845 20.845 0 01-1.44-4.282m3.102.069a18.03 18.03 0 01-.59-4.59c0-1.586.205-3.124.59-4.59m0 9.18a23.848 23.848 0 018.835 2.535M10.34 6.66a23.847 23.847 0 008.835-2.535m0 0A23.74 23.74 0 0018.795 3m.38 1.125a23.91 23.91 0 011.014 5.395m-1.014 8.855c-.118.38-.245.754-.38 1.125m.38-1.125a23.91 23.91 0 001.014-5.395m0-3.46c.495.43.816 1.035.255 1.41l-2.05 1.32a2.25 2.25 0 01-2.45 0l-2.05-1.32c-.56-.375-.24-.98.255-1.41m9.9-2.94c.495-.43.816-1.035.255-1.41l-2.05-1.32a2.25 2.25 0 00-2.45 0l-2.05 1.32c-.56.375-.24.98.255 1.41"/>
  </svg>
  <span id="announcement-badge" style="display:none;position:absolute;top:4px;right:8px;background:#ef4444;color:#fff;border-radius:50%;width:16px;height:16px;font-size:9px;font-weight:700;align-items:center;justify-content:center;"></span>
  <span>Новости</span>
</a>
```

- [ ] **Step 2: Update SSE listener for announcements**

In the chat SSE block (`base.html:490-572`), extend `applyNotify` or add separate `announcement` branch:

```javascript
function applyNotify(data) {
  if (data.type === 'announcement') {
    const badge = document.getElementById('announcement-badge');
    if (badge) {
      badge.textContent = '!';
      badge.style.display = 'flex';
    }
    if (location.pathname !== '/announcements' && !location.pathname.startsWith('/a/')) {
      showToast('📢 ' + (data.title || 'Новое объявление'), 'info');
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('HatiApp — объявление', {
          body: data.title || 'Новое объявление',
          icon: '/static/icon-192.png',
        });
      }
    }
    return;
  }
  // existing chat logic...
}
```

---

### Task 8: Service Worker Announcement Handler

**Files:**
- Modify: `static/sw.js`

- [ ] **Step 1: Add push listener for announcements**

If `static/sw.js` already has push handler, add `announcement` type branch. Otherwise append:

```javascript
self.addEventListener('push', function(event) {
  let data = {};
  try { data = event.data.json(); } catch(e) {}
  if (data.type === 'announcement') {
    event.waitUntil(
      self.registration.showNotification('HatiApp — объявление', {
        body: data.title || 'Новое объявление',
        icon: '/static/icon-192.png',
        data: { url: data.post_id ? '/a/' + data.post_id : '/announcements' },
      })
    );
  }
});
```

---

### Task 9: Tests

**Files:**
- Create: `tests/test_announcements.py`

- [ ] **Step 1: Test fixtures and helpers**

```python
import pytest
from io import BytesIO
from services.auth import hash_password
import models


@pytest.fixture
def admin_user(db):
    u = models.User(username="admin_test", password_hash=hash_password("admin"), role="admin", full_name="Admin", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def volunteer_user(db):
    u = models.User(username="vol_test", password_hash=hash_password("vol"), role="volunteer", full_name="Volunteer", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def leader_user(db):
    u = models.User(username="leader_test", password_hash=hash_password("leader"), role="leader", full_name="Leader", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _login(client, username, password):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
```

- [ ] **Step 2: Test create announcement**

```python
def test_create_announcement(client, volunteer_user):
    _login(client, "vol_test", "vol")
    res = client.post("/api/announcements", data={"content": "Hello world"})
    assert res.status_code == 200
    data = res.json()
    assert data["content"] == "Hello world"
    assert data["author"]["username"] == "vol_test"
```

- [ ] **Step 3: Test edit by author and moderator**

```python
def test_edit_announcement_by_author(client, volunteer_user):
    _login(client, "vol_test", "vol")
    post = client.post("/api/announcements", data={"content": "Original"}).json()
    res = client.put(f"/api/announcements/{post['id']}", data={"content": "Updated"})
    assert res.status_code == 200
    assert res.json()["content"] == "Updated"


def test_edit_announcement_by_moderator(client, volunteer_user, admin_user):
    client.post("/login", data={"username": "vol_test", "password": "vol"}, follow_redirects=False)
    post = client.post("/api/announcements", data={"content": "Original"}).json()
    _login(client, "admin_test", "admin")
    res = client.put(f"/api/announcements/{post['id']}", data={"content": "Admin edit"})
    assert res.status_code == 200
    assert res.json()["content"] == "Admin edit"


def test_edit_announcement_by_other_fails(client, volunteer_user, admin_user):
    _login(client, "admin_test", "admin")
    post = client.post("/api/announcements", data={"content": "Admin post"}).json()
    _login(client, "vol_test", "vol")
    res = client.put(f"/api/announcements/{post['id']}", data={"content": "Hacked"})
    assert res.status_code == 403
```

- [ ] **Step 4: Test pin/unpin and max 3**

```python
def test_pin_unpin_authorized(client, admin_user, volunteer_user):
    _login(client, "vol_test", "vol")
    post = client.post("/api/announcements", data={"content": "Post"}).json()
    _login(client, "admin_test", "admin")
    res = client.post(f"/api/announcements/{post['id']}/pin")
    assert res.status_code == 200
    assert res.json()["is_pinned"] is True


def test_pin_unpin_unauthorized_fails(client, admin_user, volunteer_user):
    _login(client, "admin_test", "admin")
    post = client.post("/api/announcements", data={"content": "Post"}).json()
    _login(client, "vol_test", "vol")
    res = client.post(f"/api/announcements/{post['id']}/pin")
    assert res.status_code == 403


def test_max_three_pinned(client, admin_user):
    _login(client, "admin_test", "admin")
    posts = []
    for i in range(3):
        p = client.post("/api/announcements", data={"content": f"Post {i}", "is_pinned": "true"}).json()
        posts.append(p)
    res = client.post(f"/api/announcements/{posts[0]['id']}/pin")
    assert res.status_code == 400
```

- [ ] **Step 5: Test feed pagination and single page**

```python
def test_feed_pagination(client, admin_user):
    _login(client, "admin_test", "admin")
    for i in range(5):
        client.post("/api/announcements", data={"content": f"Post {i}"})
    res = client.get("/api/announcements?limit=2&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert len(data["posts"]) == 2


def test_single_post_page(client, admin_user):
    _login(client, "admin_test", "admin")
    post = client.post("/api/announcements", data={"title": "Title", "content": "Body"}).json()
    res = client.get(f"/a/{post['id']}")
    assert res.status_code == 200
    assert "Title" in res.text
```

- [ ] **Step 6: Test attachments**

```python
def test_image_attachment_validation(client, admin_user):
    _login(client, "admin_test", "admin")
    img = BytesIO(b"fake image data")
    res = client.post(
        "/api/announcements",
        data={"content": "With image"},
        files={"files": ("image.png", img, "image/png")},
    )
    assert res.status_code == 200
    assert len(res.json()["attachments"]) == 1
    assert res.json()["attachments"][0]["type"] == "image"


def test_invalid_attachment_rejected(client, admin_user):
    _login(client, "admin_test", "admin")
    f = BytesIO(b"not an image")
    res = client.post(
        "/api/announcements",
        data={"content": "Bad file"},
        files={"files": ("file.exe", f, "application/octet-stream")},
    )
    assert res.status_code == 400
```

---

### Task 10: Verification

- [ ] **Step 1: Run new tests**

```bash
pytest tests/test_announcements.py -v
```

Expected: all pass.

- [ ] **Step 2: Run full test suite**

```bash
pytest
```

Expected: all previous tests still pass.

- [ ] **Step 3: Manual smoke test**

Run server, open `/announcements`, create post, verify `/a/{id}`, pin, edit, delete.

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| Create posts with title/content/attachments | Task 3 |
| Image/video attachments with size limits | Task 3 |
| Pinned posts at top, max 3 | Task 3 |
| Pagination | Task 3, Task 5 |
| Separate page `/a/{id}` | Task 3, Task 6 |
| Edit/delete permissions | Task 3, Task 9 |
| Pin permissions | Task 3, Task 9 |
| Inline editing | Task 6 |
| SSE notifications | Task 3, Task 7, Task 8 |
| Navigation tab | Task 7 |
| Tests | Task 9, Task 10 |

No gaps.
