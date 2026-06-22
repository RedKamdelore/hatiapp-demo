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
def viewer(db):
    u = models.User(
        username=f"viewer_{uuid.uuid4().hex[:6]}",
        full_name="Viewer",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


@pytest.fixture
def target(db):
    u = models.User(
        username=f"target_{uuid.uuid4().hex[:6]}",
        full_name="Target",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


def test_user_upcoming_shifts_returns_future_only(client, viewer, target, direction, db):
    future_slot = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=2),
        time=time(10, 0),
        capacity=2,
    )
    today_slot = models.Slot(
        direction_id=direction.id,
        date=date.today(),
        time=time(14, 0),
        capacity=2,
    )
    db.add_all([future_slot, today_slot])
    db.commit()

    future_booking = models.Booking(user_id=target.id, slot_id=future_slot.id)
    today_booking = models.Booking(user_id=target.id, slot_id=today_slot.id)
    db.add_all([future_booking, today_booking])
    db.commit()

    _set_session(client, viewer)
    res = client.get(f"/api/users/{target.id}/upcoming-shifts")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["booking_id"] == future_booking.id
    assert data[0]["slot_id"] == future_slot.id
    assert data[0]["direction"] == direction.name
    assert data[0]["date"] == future_slot.date.isoformat()
    assert data[0]["time"] == "10:00:00"


def test_user_upcoming_shifts_404_for_missing_user(client, viewer):
    _set_session(client, viewer)
    res = client.get("/api/users/99999/upcoming-shifts")
    assert res.status_code == 404


def test_user_upcoming_shifts_401_for_anonymous(client, target):
    res = client.get(f"/api/users/{target.id}/upcoming-shifts")
    assert res.status_code == 401
