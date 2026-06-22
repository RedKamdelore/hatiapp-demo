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
