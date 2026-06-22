import pytest
from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS, ROLE_VOLUNTEER, COOKIE_NAME
import models
from datetime import date, time


class TestSlotDescription:
    @pytest.fixture
    def admin_client(self, client, admin_user):
        client.cookies.set(COOKIE_NAME, sign_cookie(admin_user.id))
        return client

    @pytest.fixture
    def volunteer_client(self, client, test_user):
        client.cookies.set(COOKIE_NAME, sign_cookie(test_user.id))
        return client

    @pytest.fixture
    def leader_user(self, db):
        user = models.User(
            username="leaderuser",
            full_name="Leader User",
            password_hash=hash_password("leaderpass"),
            role=ROLE_LEADER,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user
        db.delete(user)
        db.commit()

    @pytest.fixture
    def direction(self, db):
        d = models.Direction(name="Test Direction")
        db.add(d)
        db.commit()
        db.refresh(d)
        yield d
        db.delete(d)
        db.commit()

    @pytest.fixture
    def slot(self, db, direction):
        s = models.Slot(
            direction_id=direction.id,
            date=date(2026, 7, 9),
            time=time(10, 0),
            capacity=5,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        yield s
        db.delete(s)
        db.commit()

    def test_admin_can_update_description(self, admin_client, slot, db):
        response = admin_client.post(
            f"/api/slot/{slot.id}/description",
            data={"description": "Приготовить обед"},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        db.refresh(slot)
        assert slot.description == "Приготовить обед"

    def test_volunteer_cannot_update_description(self, volunteer_client, slot, db):
        response = volunteer_client.post(
            f"/api/slot/{slot.id}/description",
            data={"description": "Взлом"},
        )
        assert response.status_code == 403

        db.refresh(slot)
        assert slot.description is None

    def test_leader_can_update_own_direction(self, client, leader_user, direction, slot, db):
        # Назначаем руководителя направления
        db.add(models.DirectionLeader(direction_id=direction.id, user_id=leader_user.id))
        db.commit()

        client.cookies.set(COOKIE_NAME, sign_cookie(leader_user.id))
        response = client.post(
            f"/api/slot/{slot.id}/description",
            data={"description": "Своя смена"},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        db.refresh(slot)
        assert slot.description == "Своя смена"

    def test_leader_cannot_update_other_direction(self, client, leader_user, direction, slot, db):
        # leader_user не назначен на direction
        client.cookies.set(COOKIE_NAME, sign_cookie(leader_user.id))
        response = client.post(
            f"/api/slot/{slot.id}/description",
            data={"description": "Чужая смена"},
        )
        assert response.status_code == 403

        db.refresh(slot)
        assert slot.description is None

    def test_empty_description_becomes_null(self, admin_client, slot, db):
        response = admin_client.post(
            f"/api/slot/{slot.id}/description",
            data={"description": "   "},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        db.refresh(slot)
        assert slot.description is None

    def test_update_nonexistent_slot(self, admin_client):
        response = admin_client.post(
            "/api/slot/99999/description",
            data={"description": "Тест"},
        )
        assert response.status_code == 404
