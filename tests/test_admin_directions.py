import pytest
from datetime import date, time
from services.auth import hash_password
from config import ROLE_VOLUNTEER
import models


@pytest.fixture
def direction(db):
    d = models.Direction(name="Test Direction", description="Original")
    db.add(d)
    db.commit()
    db.refresh(d)
    direction_id = d.id
    yield d
    existing = db.query(models.Direction).filter_by(id=direction_id).first()
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

    try:
        response = client.post(f"/admin/direction/{direction.id}/edit", data={
            "name": "Other Direction",
        }, follow_redirects=False)
        assert response.status_code == 302
        assert "toast_type=error" in (response.headers.get("location") or "")
    finally:
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


def test_delete_direction_with_preferences_and_attendance(client, admin_with_session, direction, db):
    user = models.User(username="pref_user", full_name="Pref User", password_hash=hash_password("p"), role=ROLE_VOLUNTEER, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        db.add(models.UserPreference(user_id=user.id, direction_id=direction.id))
        slot = models.Slot(direction_id=direction.id, date=date(2026, 6, 15), time=time(10, 0, 0), capacity=5)
        db.add(slot)
        db.commit()
        db.refresh(slot)

        booking = models.Booking(user_id=user.id, slot_id=slot.id)
        db.add(booking)
        db.commit()
        db.refresh(booking)

        db.add(models.Attendance(booking_id=booking.id, present=True))
        db.commit()

        response = client.post(f"/admin/direction/{direction.id}/delete", follow_redirects=False)
        assert response.status_code == 302
        assert db.query(models.Direction).filter_by(id=direction.id).first() is None
    finally:
        db.delete(user)
        db.commit()
