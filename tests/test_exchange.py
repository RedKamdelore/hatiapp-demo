import pytest
import uuid
from datetime import date, time, datetime, timedelta

from services.auth import hash_password, sign_cookie
from services import exchange as exchange_service
from config import (
    ROLE_VOLUNTEER,
    ROLE_ADMIN,
    ROLE_LEADER,
    ROLE_LOTOS,
    ROLE_PERMANENT,
    COOKIE_NAME,
)
import models


def _set_session(client, user):
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))


@pytest.fixture
def direction(db):
    d = models.Direction(name=f"Dir_{uuid.uuid4().hex[:8]}")
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
def sender(db):
    u = models.User(
        username=f"sender_{uuid.uuid4().hex[:8]}",
        full_name="Sender",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


@pytest.fixture
def receiver(db):
    u = models.User(
        username=f"receiver_{uuid.uuid4().hex[:8]}",
        full_name="Receiver",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


@pytest.fixture
def bookings(db, sender, receiver, slot_a, slot_b):
    ba = models.Booking(user_id=sender.id, slot_id=slot_a.id)
    bb = models.Booking(user_id=receiver.id, slot_id=slot_b.id)
    db.add_all([ba, bb])
    db.commit()
    db.refresh(ba)
    db.refresh(bb)
    return ba, bb


@pytest.fixture
def proposal(db, sender, receiver, bookings, client):
    ba, bb = bookings
    _set_session(client, sender)
    res = client.post("/api/exchange-proposals", data={
        "receiver_id": receiver.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    })
    assert res.status_code == 200
    proposal_id = res.json()["id"]
    p = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    yield p


def test_create_exchange_proposal(client, sender, receiver, bookings):
    ba, bb = bookings
    _set_session(client, sender)
    res = client.post("/api/exchange-proposals", data={
        "receiver_id": receiver.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"
    assert data["sender_id"] == sender.id
    assert data["receiver_id"] == receiver.id


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS, ROLE_PERMANENT])
def test_non_volunteer_cannot_create(client, db, sender, receiver, bookings, role):
    ba, bb = bookings
    unique = uuid.uuid4().hex[:8]
    user = models.User(
        username=f"nonvol_{role}_{unique}",
        full_name=f"Non Volunteer {role}",
        password_hash=hash_password("p"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _set_session(client, user)
    res = client.post("/api/exchange-proposals", data={
        "receiver_id": receiver.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    })
    assert res.status_code in (400, 403)


def test_accept_exchange_swaps_owners(client, db, sender, receiver, proposal, bookings):
    ba, bb = bookings
    _set_session(client, receiver)
    res = client.post(f"/api/exchange-proposals/{proposal.id}/accept")
    assert res.status_code == 200

    db.refresh(ba)
    db.refresh(bb)
    assert ba.user_id == receiver.id
    assert bb.user_id == sender.id


def test_accept_fails_on_time_conflict(client, db, sender, receiver, slot_a, slot_b, bookings):
    ba, bb = bookings

    other_direction = models.Direction(name=f"Dir2_{uuid.uuid4().hex[:8]}")
    db.add(other_direction)
    db.commit()
    db.refresh(other_direction)

    conflict_slot = models.Slot(
        direction_id=other_direction.id,
        date=slot_b.date,
        time=slot_b.time,
        capacity=2,
    )
    db.add(conflict_slot)
    db.commit()
    db.refresh(conflict_slot)

    conflict_booking = models.Booking(user_id=sender.id, slot_id=conflict_slot.id)
    db.add(conflict_booking)
    db.commit()

    _set_session(client, sender)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": receiver.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, receiver)
    res = client.post(f"/api/exchange-proposals/{prop['id']}/accept")
    assert res.status_code == 400


def test_accept_fails_on_duplicate_slot(client, db, sender, receiver, slot_a, slot_b, bookings):
    ba, bb = bookings

    duplicate_booking = models.Booking(user_id=sender.id, slot_id=slot_b.id)
    db.add(duplicate_booking)
    db.commit()

    _set_session(client, sender)
    prop = client.post("/api/exchange-proposals", data={
        "receiver_id": receiver.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    }).json()

    _set_session(client, receiver)
    res = client.post(f"/api/exchange-proposals/{prop['id']}/accept")
    assert res.status_code == 400


def test_decline_exchange(client, db, sender, receiver, proposal):
    _set_session(client, receiver)
    res = client.post(f"/api/exchange-proposals/{proposal.id}/decline")
    assert res.status_code == 200
    db.refresh(proposal)
    assert proposal.status == "declined"


def test_cancel_exchange(client, db, sender, receiver, proposal):
    _set_session(client, sender)
    res = client.post(f"/api/exchange-proposals/{proposal.id}/cancel")
    assert res.status_code == 200
    db.refresh(proposal)
    assert proposal.status == "cancelled"


def test_expire_exchange(db, sender, receiver, bookings):
    ba, bb = bookings
    proposal, _ = exchange_service.create_proposal(
        sender, receiver.id, ba.id, bb.id, db
    )
    proposal.expires_at = datetime.now() - timedelta(minutes=1)
    db.commit()

    count = exchange_service.expire_pending_proposals(db)
    assert count == 1
    db.refresh(proposal)
    assert proposal.status == "expired"


def test_exchange_logged(client, db, sender, receiver, proposal):
    _set_session(client, receiver)
    res = client.post(f"/api/exchange-proposals/{proposal.id}/accept")
    assert res.status_code == 200

    log = (
        db.query(models.ActivityLog)
        .filter_by(action="exchange_accepted", user_id=receiver.id, target_id=sender.id)
        .first()
    )
    assert log is not None


def test_chat_message_created(client, db, sender, receiver, bookings):
    ba, bb = bookings
    _set_session(client, sender)
    res = client.post("/api/exchange-proposals", data={
        "receiver_id": receiver.id,
        "sender_booking_id": ba.id,
        "receiver_booking_id": bb.id,
    })
    assert res.status_code == 200
    data = res.json()

    msg = db.query(models.ChatMessage).filter(
        models.ChatMessage.sender_id == sender.id,
        models.ChatMessage.receiver_id == receiver.id,
    ).first()
    assert msg is not None
    assert msg.payload["type"] == "exchange_proposal"
    assert msg.payload["proposal_id"] == data["id"]


def test_chat_card_status_updated(client, db, sender, receiver, proposal):
    _set_session(client, receiver)
    res = client.post(f"/api/exchange-proposals/{proposal.id}/accept")
    assert res.status_code == 200

    msgs = db.query(models.ChatMessage).filter(
        models.ChatMessage.payload.isnot(None)
    ).all()
    card = next((m for m in msgs if m.payload.get("proposal_id") == proposal.id), None)
    assert card is not None
    assert card.payload["status"] == "accepted"
