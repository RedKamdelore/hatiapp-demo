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

    def test_unread_chat_count(self, volunteer_client, test_user, db):
        response = volunteer_client.get("/api/unread-chat-count")
        assert response.status_code == 200
        assert response.json() == {"unread": 0}
