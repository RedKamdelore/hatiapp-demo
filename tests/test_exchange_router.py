import pytest
from datetime import date, time, timedelta
from services.auth import hash_password, sign_cookie
from config import ROLE_VOLUNTEER, COOKIE_NAME
import models
import uuid


def _set_session(client, user):
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))


@pytest.fixture
def direction(db):
    d = models.Direction(name=f"Dir_{uuid.uuid4().hex[:6]}")
    db.add(d)
    db.commit()
    db.refresh(d)
    yield d


@pytest.fixture
def slot_a(db, direction):
    s = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=2),
        time=time(10, 0),
        capacity=2,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    yield s


@pytest.fixture
def slot_b(db, direction):
    s = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=3),
        time=time(14, 0),
        capacity=2,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    yield s


@pytest.fixture
def vol_a(db):
    u = models.User(
        username=f"va_{uuid.uuid4().hex[:6]}",
        full_name="Vol A",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


@pytest.fixture
def vol_b(db):
    u = models.User(
        username=f"vb_{uuid.uuid4().hex[:6]}",
        full_name="Vol B",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


def test_create_exchange_proposal_creates_chat_message(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb])
    db.commit()

    _set_session(client, vol_a)
    res = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"

    msg = db.query(models.ChatMessage).filter(
        models.ChatMessage.sender_id == vol_a.id,
        models.ChatMessage.receiver_id == vol_b.id,
    ).first()
    assert msg is not None
    assert msg.payload["type"] == "exchange_proposal"
    assert msg.payload["proposal_id"] == data["id"]


def test_accept_exchange_swaps_owners_and_updates_payload(client, vol_a, vol_b, slot_a, slot_b, db):
    ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
    db.add_all([ba, bb])
    db.commit()

    _set_session(client, vol_a)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": vol_b.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, vol_b)
    res = client.post(f"/api/exchange-proposals/{prop['id']}/accept")
    assert res.status_code == 200

    db.refresh(ba)
    db.refresh(bb)
    assert ba.user_id == vol_b.id
    assert bb.user_id == vol_a.id

    msg = db.query(models.ChatMessage).filter(
        models.ChatMessage.payload.isnot(None)
    ).all()
    card = next((m for m in msg if m.payload.get("proposal_id") == prop["id"]), None)
    assert card is not None
    assert card.payload["status"] == "accepted"
