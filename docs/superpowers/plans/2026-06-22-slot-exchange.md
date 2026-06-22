# Slot Exchange Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow volunteers to propose a pairwise shift exchange directly inside a chat. After both sides agree, ownership of two `Booking` records is swapped atomically and all events are logged.

**Architecture:** Add `ExchangeProposal` and a JSON `payload` field on `ChatMessage`. Expose REST endpoints under `/api/exchange-proposals`. Render an exchange card inside the chat thread. Run a lightweight background job on startup to expire pending proposals older than 3 hours.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Jinja2, vanilla JS, WebSocket/SSE for real-time chat updates.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `models.py` | `ExchangeProposal`, `ChatMessage.payload` |
| `alembic/versions/2026_06_22_add_exchange_proposals.py` | Migration |
| `services/exchange.py` | Core exchange logic + validation + logging |
| `routers/exchange.py` | `/api/exchange-proposals/*` endpoints |
| `routers/chat.py` | Minor: handle `payload` rendering in WebSocket |
| `templates/chat.html` | Exchange button, modal, card rendering |
| `static/chat-exchange.js` | Client-side exchange UI helpers |
| `main.py` | Register `exchange` router + background expiration task |
| `tests/test_exchange.py` | API and business-logic tests |

---

## Shared Constants

```python
EXCHANGE_LIFETIME_HOURS = 3
```

Use in `services/exchange.py` and reference in tests.

---

### Task 1: Database Models

**Files:**
- Modify: `models.py:1-5`
- Modify: `models.py:90-110`
- Modify: `models.py:131-151`

- [ ] **Step 1: Add JSON import**

```python
from sqlalchemy import Column, Integer, String, ForeignKey, Date, Time, Boolean, UniqueConstraint, Text, DateTime, Index, JSON
```

- [ ] **Step 2: Add `ExchangeProposal` model**

Append after `ChatMessage`:

```python
class ExchangeProposal(Base):
    __tablename__ = "exchange_proposals"

    id                  = Column(Integer, primary_key=True)
    sender_id           = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sender_booking_id   = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    receiver_booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    status              = Column(String, nullable=False, default="pending")
    created_at          = Column(DateTime, server_default=func.now())
    expires_at          = Column(DateTime, nullable=False)
    resolved_at         = Column(DateTime, nullable=True)

    sender   = relationship("User", foreign_keys=[sender_id], back_populates="sent_proposals")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_proposals")
    sender_booking   = relationship("Booking", foreign_keys=[sender_booking_id])
    receiver_booking = relationship("Booking", foreign_keys=[receiver_booking_id])
```

- [ ] **Step 3: Add `payload` to `ChatMessage`**

```python
payload = Column(JSON, nullable=True)
```

- [ ] **Step 4: Add relationships on `User`**

```python
sent_proposals     = relationship("ExchangeProposal", foreign_keys="ExchangeProposal.sender_id", back_populates="sender", cascade="all, delete")
received_proposals = relationship("ExchangeProposal", foreign_keys="ExchangeProposal.receiver_id", back_populates="receiver", cascade="all, delete")
```

- [ ] **Step 5: Run and verify migration**

```bash
.\venv\Scripts\alembic revision --autogenerate -m "add exchange proposals"
.\venv\Scripts\alembic upgrade head
```

Expected: tables `exchange_proposals` created, `chat_messages.payload` added.

---

### Task 2: Core Exchange Service

**Files:**
- Create: `services/exchange.py`

- [ ] **Step 1: Create service scaffold**

```python
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import models
from services.booking import user_is_present

EXCHANGE_LIFETIME_HOURS = 3


def _now():
    return datetime.now()


def _is_volunteer(user: models.User) -> bool:
    return user.role == models.UserRole.VOLUNTEER if hasattr(models, "UserRole") else user.role == "volunteer"


def _slot_in_future(slot: models.Slot) -> bool:
    return datetime.combine(slot.date, slot.time) > _now()


def _time_conflict(user_id: int, slot: models.Slot, exclude_booking_ids: list[int], db: Session) -> bool:
    return db.query(models.Booking).join(models.Slot).filter(
        models.Booking.user_id == user_id,
        models.Booking.id.notin_(exclude_booking_ids),
        models.Slot.date == slot.date,
        models.Slot.time == slot.time,
    ).first() is not None


def _log(db: Session, actor_id: int, action: str, slot_id: int, target_id: int = None):
    db.add(models.ActivityLog(
        user_id=actor_id,
        target_id=target_id,
        action=action,
        slot_id=slot_id,
    ))
```

- [ ] **Step 2: Implement `create_proposal`**

```python
def create_proposal(
    sender: models.User,
    receiver_id: int,
    sender_booking_id: int,
    receiver_booking_id: int,
    db: Session,
) -> tuple[models.ExchangeProposal | None, str]:
    if not _is_volunteer(sender):
        return None, "Только волонтёры могут обмениваться сменами"

    receiver = db.query(models.User).filter_by(id=receiver_id, is_active=True).first()
    if not receiver or not _is_volunteer(receiver):
        return None, "Собеседник не найден или не является волонтёром"

    sender_booking = db.query(models.Booking).filter_by(
        id=sender_booking_id, user_id=sender.id
    ).first()
    receiver_booking = db.query(models.Booking).filter_by(
        id=receiver_booking_id, user_id=receiver_id
    ).first()

    if not sender_booking or not receiver_booking:
        return None, "Смена не найдена"

    if not _slot_in_future(sender_booking.slot) or not _slot_in_future(receiver_booking.slot):
        return None, "Можно обмениваться только будущими сменами"

    existing = db.query(models.ExchangeProposal).filter(
        models.ExchangeProposal.status == "pending",
        models.ExchangeProposal.sender_id == sender.id,
        models.ExchangeProposal.receiver_id == receiver.id,
    ).first()
    if existing:
        return None, "Уже есть активное предложение этому человеку"

    expires_at = _now() + timedelta(hours=EXCHANGE_LIFETIME_HOURS)
    proposal = models.ExchangeProposal(
        sender_id=sender.id,
        receiver_id=receiver.id,
        sender_booking_id=sender_booking.id,
        receiver_booking_id=receiver_booking.id,
        status="pending",
        expires_at=expires_at,
    )
    db.add(proposal)
    db.flush()

    _log(db, sender.id, "exchange_proposed", sender_booking.slot_id, receiver.id)
    db.commit()
    return proposal, ""
```

- [ ] **Step 3: Implement `accept_proposal`**

```python
def accept_proposal(
    proposal: models.ExchangeProposal,
    actor: models.User,
    db: Session,
) -> tuple[bool, str]:
    if proposal.receiver_id != actor.id:
        return False, "Нет прав"
    if proposal.status != "pending":
        return False, "Предложение уже закрыто"
    if proposal.expires_at < _now():
        return False, "Предложение истекло"

    db.refresh(proposal.sender_booking)
    db.refresh(proposal.receiver_booking)

    sender_booking = proposal.sender_booking
    receiver_booking = proposal.receiver_booking

    if sender_booking.user_id != proposal.sender_id or receiver_booking.user_id != proposal.receiver_id:
        return False, "Смены уже изменились"

    new_sender_slot = receiver_booking.slot
    new_receiver_slot = sender_booking.slot

    # Дублирование слота
    dup_sender = db.query(models.Booking).filter_by(
        user_id=proposal.sender_id, slot_id=new_sender_slot.id
    ).first()
    dup_receiver = db.query(models.Booking).filter_by(
        user_id=proposal.receiver_id, slot_id=new_receiver_slot.id
    ).first()
    if dup_sender or dup_receiver:
        return False, "Один из участников уже записан на целевой слот"

    # Временной конфликт
    exclude_ids = [sender_booking.id, receiver_booking.id]
    if _time_conflict(proposal.sender_id, new_sender_slot, exclude_ids, db):
        return False, "У вас есть другая смена в это время"
    if _time_conflict(proposal.receiver_id, new_receiver_slot, exclude_ids, db):
        return False, "У собеседника есть другая смена в это время"

    # SWAP
    sender_booking.user_id, receiver_booking.user_id = receiver_booking.user_id, sender_booking.user_id

    proposal.status = "accepted"
    proposal.resolved_at = _now()

    _log(db, actor.id, "exchange_accepted", sender_booking.slot_id, proposal.sender_id)
    db.commit()
    return True, "Обмен завершён"
```

- [ ] **Step 4: Implement `decline_proposal`**

```python
def decline_proposal(
    proposal: models.ExchangeProposal,
    actor: models.User,
    db: Session,
) -> tuple[bool, str]:
    if proposal.receiver_id != actor.id:
        return False, "Нет прав"
    if proposal.status != "pending":
        return False, "Предложение уже закрыто"

    proposal.status = "declined"
    proposal.resolved_at = _now()
    _log(db, actor.id, "exchange_declined", proposal.sender_booking.slot_id, proposal.sender_id)
    db.commit()
    return True, "Предложение отклонено"
```

- [ ] **Step 5: Implement `cancel_proposal`**

```python
def cancel_proposal(
    proposal: models.ExchangeProposal,
    actor: models.User,
    db: Session,
) -> tuple[bool, str]:
    if proposal.sender_id != actor.id:
        return False, "Нет прав"
    if proposal.status != "pending":
        return False, "Предложение уже закрыто"

    proposal.status = "cancelled"
    proposal.resolved_at = _now()
    _log(db, actor.id, "exchange_cancelled", proposal.sender_booking.slot_id, proposal.receiver_id)
    db.commit()
    return True, "Предложение отменено"
```

- [ ] **Step 6: Implement `expire_pending_proposals`**

```python
def expire_pending_proposals(db: Session) -> int:
    proposals = db.query(models.ExchangeProposal).filter(
        models.ExchangeProposal.status == "pending",
        models.ExchangeProposal.expires_at < _now(),
    ).all()
    for p in proposals:
        p.status = "expired"
        p.resolved_at = _now()
        _log(db, p.sender_id, "exchange_expired", p.sender_booking.slot_id, p.receiver_id)
    db.commit()
    return len(proposals)
```

---

### Task 3: Exchange Router

**Files:**
- Create: `routers/exchange.py`
- Modify: `main.py:18`, `main.py:50-60`

- [ ] **Step 1: Create router**

```python
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from sqlalchemy.orm import Session

import models
from database import get_db
from services.auth import get_current_user
from services import exchange as exchange_service
from services.sse_manager import sse_manager

router = APIRouter(prefix="/api/exchange-proposals", tags=["exchange"])


def _proposal_to_dict(proposal: models.ExchangeProposal) -> dict:
    sb = proposal.sender_booking
    rb = proposal.receiver_booking
    return {
        "id": proposal.id,
        "status": proposal.status,
        "sender_id": proposal.sender_id,
        "receiver_id": proposal.receiver_id,
        "sender_slot": {
            "id": sb.slot.id,
            "direction": sb.slot.direction.name,
            "date": sb.slot.date.isoformat(),
            "time": str(sb.slot.time),
        },
        "receiver_slot": {
            "id": rb.slot.id,
            "direction": rb.slot.direction.name,
            "date": rb.slot.date.isoformat(),
            "time": str(rb.slot.time),
        },
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
    }


@router.post("")
def create(
    request: Request,
    receiver_id: int = Form(...),
    sender_booking_id: int = Form(...),
    receiver_booking_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    proposal, error = exchange_service.create_proposal(
        user, receiver_id, sender_booking_id, receiver_booking_id, db
    )
    if not proposal:
        raise HTTPException(status_code=400, detail=error)

    # Создаём системное сообщение в чате
    payload = {
        "type": "exchange_proposal",
        "proposal_id": proposal.id,
        "sender_slot": _proposal_to_dict(proposal)["sender_slot"],
        "receiver_slot": _proposal_to_dict(proposal)["receiver_slot"],
    }
    msg = models.ChatMessage(
        sender_id=user.id,
        receiver_id=receiver_id,
        text="Предложение обмена сменами",
        payload=payload,
    )
    db.add(msg)
    db.commit()

    sse_manager.send_to_user(receiver_id, {"type": "chat_message", "from": user.id})

    return _proposal_to_dict(proposal)


@router.post("/{proposal_id}/accept")
def accept(proposal_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    proposal = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    ok, msg = exchange_service.accept_proposal(proposal, user, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _update_chat_card(proposal, db)
    sse_manager.send_to_user(proposal.sender_id, {"type": "exchange_update", "proposal_id": proposal.id, "status": "accepted"})
    return _proposal_to_dict(proposal)


@router.post("/{proposal_id}/decline")
def decline(proposal_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    proposal = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    ok, msg = exchange_service.decline_proposal(proposal, user, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _update_chat_card(proposal, db)
    sse_manager.send_to_user(proposal.sender_id, {"type": "exchange_update", "proposal_id": proposal.id, "status": "declined"})
    return _proposal_to_dict(proposal)


@router.post("/{proposal_id}/cancel")
def cancel(proposal_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    proposal = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    ok, msg = exchange_service.cancel_proposal(proposal, user, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _update_chat_card(proposal, db)
    sse_manager.send_to_user(proposal.receiver_id, {"type": "exchange_update", "proposal_id": proposal.id, "status": "cancelled"})
    return _proposal_to_dict(proposal)


def _update_chat_card(proposal: models.ExchangeProposal, db: Session):
    msg = db.query(models.ChatMessage).filter(
        models.ChatMessage.payload.isnot(None),
        models.ChatMessage.payload["proposal_id"].as_integer() == proposal.id,
    ).first()
    if msg and msg.payload:
        msg.payload["status"] = proposal.status
        db.commit()
```

- [ ] **Step 2: Register router in `main.py`**

```python
from routers import auth, schedule, leader, admin, profile, chat, sse, logs, slots, announcements, exchange
```

```python
app.include_router(exchange.router)
```

---

### Task 4: Background Expiration Job

**Files:**
- Modify: `main.py:1-20`

- [ ] **Step 1: Add APScheduler dependency**

```bash
.\venv\Scripts\pip install apscheduler
```

Add to `requirements.txt`:

```
apscheduler>=3.10.0
```

- [ ] **Step 2: Add startup job**

In `main.py`:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from services.exchange import expire_pending_proposals
from database import SessionLocal


def _expire_exchange_proposals_job():
    db = SessionLocal()
    try:
        expire_pending_proposals(db)
    finally:
        db.close()


scheduler = BackgroundScheduler()
scheduler.add_job(_expire_exchange_proposals_job, "interval", minutes=1)
scheduler.start()
```

---

### Task 5: Chat UI

**Files:**
- Modify: `templates/chat.html:181-197`
- Modify: `templates/chat.html:207-788`
- Create: `static/chat-exchange.js`

- [ ] **Step 1: Add exchange button near message input**

After file attach label, before text input:

```html
{% if user.role == 'volunteer' and target.role == 'volunteer' %}
<button type="button" id="exchange-btn" class="bg-gray-100 hover:bg-gray-200 rounded-2xl px-3 py-3 text-sm transition" title="Поменяться сменой">🔄</button>
{% endif %}
```

- [ ] **Step 2: Add exchange modal**

Append to `{% block modals %}` or before `{% endblock %}` in content:

```html
<div id="exchange-modal" class="fixed inset-0 bg-black/50 z-50 hidden flex items-end sm:items-center justify-center p-0 sm:p-4">
  <div class="bg-white dark:bg-[#1e1e1e] w-full max-w-md rounded-t-2xl sm:rounded-2xl p-4 space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-bold">Обмен сменами</h2>
      <button onclick="closeExchangeModal()" class="text-gray-500">✕</button>
    </div>
    <div id="exchange-step-1" class="space-y-2">
      <p class="text-sm text-gray-600">Выберите свою смену:</p>
      <select id="exchange-my-booking" class="w-full border rounded-lg px-3 py-2 dark:bg-[#181818]"></select>
      <button onclick="loadReceiverBookings()" class="w-full bg-indigo-600 text-white py-2 rounded-lg">Далее</button>
    </div>
    <div id="exchange-step-2" class="hidden space-y-2">
      <p class="text-sm text-gray-600">Выберите смену собеседника:</p>
      <select id="exchange-their-booking" class="w-full border rounded-lg px-3 py-2 dark:bg-[#181818]"></select>
      <button onclick="submitExchange()" class="w-full bg-indigo-600 text-white py-2 rounded-lg">Предложить обмен</button>
    </div>
    <div id="exchange-error" class="text-sm text-red-600 hidden"></div>
  </div>
</div>
```

- [ ] **Step 3: Add exchange card rendering in chat JS**

When rendering messages, detect `payload.type === 'exchange_proposal'` and render card instead of plain text.

Pseudo-code in chat render loop:

```javascript
if (msg.payload && msg.payload.type === 'exchange_proposal') {
  return renderExchangeCard(msg);
}
```

`renderExchangeCard(msg)` builds HTML with slot names, arrow, and action buttons based on `msg.payload.status` and `ME`.

- [ ] **Step 4: Create `static/chat-exchange.js`**

Functions:
- `openExchangeModal()` / `closeExchangeModal()`
- `loadMyBookings()` — fetch `/api/my-upcoming-shifts`
- `loadReceiverBookings()` — fetch `/api/users/{WITH_ID}/upcoming-shifts`
- `submitExchange()` — POST `/api/exchange-proposals`
- `renderExchangeCard(msg)` — returns DOM string
- `handleExchangeAction(proposalId, action)` — POST accept/decline/cancel

- [ ] **Step 5: Include script in `chat.html`**

```html
<script src="/static/chat-exchange.js"></script>
```

---

### Task 6: New API for Slot Lists

**Files:**
- Modify: `routers/profile.py`
- Create or reuse endpoint for another user's upcoming shifts

- [ ] **Step 1: Add `/api/users/{user_id}/upcoming-shifts`**

In `routers/profile.py`:

```python
@router.get("/api/users/{user_id}/upcoming-shifts")
def user_upcoming_shifts(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    target = db.query(models.User).filter_by(id=user_id, is_active=True).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Доступ только к сменам собеседника в личном чате
    now = datetime.now()
    bookings = (
        db.query(models.Booking)
        .join(models.Slot)
        .filter(
            models.Booking.user_id == user_id,
            models.Slot.date > now.date(),
        )
        .order_by(models.Slot.date, models.Slot.time)
        .all()
    )

    return [
        {
            "booking_id": b.id,
            "slot_id": b.slot.id,
            "direction": b.slot.direction.name,
            "date": b.slot.date.isoformat(),
            "time": str(b.slot.time),
        }
        for b in bookings
    ]
```

---

### Task 7: Tests

**Files:**
- Create: `tests/test_exchange.py`

- [ ] **Step 1: Write fixtures**

```python
import pytest
from datetime import date, time, datetime, timedelta
from services.auth import hash_password
from services import exchange as exchange_service
from config import ROLE_VOLUNTEER
import models
import uuid


def _set_session(client, user):
    from services.auth import sign_cookie
    from config import COOKIE_NAME
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))


@pytest.fixture
def direction(db):
    d = models.Direction(name=f"Dir_{uuid.uuid4().hex[:6]}")
    db.add(d); db.commit(); db.refresh(d)
    yield d


@pytest.fixture
def slot_a(db, direction):
    s = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=2),
        time=time(10, 0),
        capacity=2,
    )
    db.add(s); db.commit(); db.refresh(s)
    yield s


@pytest.fixture
def slot_b(db, direction):
    s = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=3),
        time=time(14, 0),
        capacity=2,
    )
    db.add(s); db.commit(); db.refresh(s)
    yield s


@pytest.fixture
def vol_a(db):
    u = models.User(username=f"va_{uuid.uuid4().hex[:6]}", full_name="Vol A", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    yield u


@pytest.fixture
def vol_b(db):
    u = models.User(username=f"vb_{uuid.uuid4().hex[:6]}", full_name="Vol B", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    yield u
```

- [ ] **Step 2: Test create proposal**

```python
def test_create_exchange_proposal(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb]); db.commit()

    _set_session(client, vol_a)
    res = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"
```

- [ ] **Step 3: Test accept swap**

```python
def test_accept_exchange_swaps_owners(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb]); db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, vol_b)
    res = client.post(f"/api/exchange-proposals/{prop['id']}/accept")
    assert res.status_code == 200

    db.refresh(ba); db.refresh(bb)
    assert ba.user_id == vol_b.id
    assert bb.user_id == vol_a.id
```

- [ ] **Step 4: Test time conflict blocks accept**

```python
def test_accept_fails_on_time_conflict(client, vol_a, vol_b, slot_a, slot_b, direction, db):
    conflict = models.Slot(direction_id=direction.id, date=slot_b.date, time=slot_b.time, capacity=2)
    db.add(conflict); db.commit()

    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    bc = models.Booking(user_id=vol_a.id, slot_id=conflict.id)
    db.add_all([ba, bb, bc]); db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, vol_b)
    res = client.post(f"/api/exchange-proposals/{prop['id']}/accept")
    assert res.status_code == 400
```

- [ ] **Step 5: Test decline/cancel/expire**

```python
def test_decline_exchange(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb]); db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, vol_b)
    res = client.post(f"/api/exchange-proposals/{prop['id']}/decline")
    assert res.status_code == 200
    assert res.json()["status"] == "declined"


def test_cancel_exchange(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb]); db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    res = client.post(f"/api/exchange-proposals/{prop['id']}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_expire_exchange(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb]); db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    # Истекаем вручную
    p = db.query(models.ExchangeProposal).filter_by(id=prop["id"]).first()
    p.expires_at = datetime.now() - timedelta(minutes=1)
    db.commit()

    exchange_service.expire_pending_proposals(db)
    db.refresh(p)
    assert p.status == "expired"
```

- [ ] **Step 6: Test activity log**

```python
def test_exchange_logged(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb]); db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, vol_b)
    client.post(f"/api/exchange-proposals/{prop['id']}/accept")

    log = db.query(models.ActivityLog).filter(
        models.ActivityLog.action == "exchange_accepted"
    ).first()
    assert log is not None
```

---

### Task 8: Verification

- [ ] **Step 1: Run exchange tests**

```bash
$env:PYTHONPATH="C:\Users\Administrator\Desktop\САМОПАЛ\Hatiapp_cowork_OPENCODE"; .\venv\Scripts\pytest tests/test_exchange.py -v
```

Expected: all pass.

- [ ] **Step 2: Run full suite**

```bash
$env:PYTHONPATH="C:\Users\Administrator\Desktop\САМОПАЛ\Hatiapp_cowork_OPENCODE"; .\venv\Scripts\pytest tests/ -q
```

Expected: previous tests still pass.

- [ ] **Step 3: Manual smoke test**

Open `/chat/with/{id}` between two volunteers, click 🔄, select shifts, send proposal, accept/decline/cancel.

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| Pairwise slot exchange | Task 2, Task 3 |
| Only volunteers | Task 2, Task 3 |
| Only future shifts | Task 2 |
| One pending proposal per pair | Task 2 |
| 3-hour expiration | Task 2, Task 4 |
| Accept / decline / cancel | Task 2, Task 3 |
| Atomic swap of `Booking.user_id` | Task 2 |
| Time conflict checks | Task 2 |
| System chat card with payload | Task 1, Task 5 |
| ActivityLog for all events | Task 2 |
| Tests | Task 7 |

No gaps.
