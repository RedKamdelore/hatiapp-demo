import pytest

from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_VOLUNTEER, ROLE_LOTOS, COOKIE_NAME
import models


@pytest.fixture
def admin_with_session(db, client):
    admin = models.User(
        username="massaction_admin",
        full_name="Mass Action Admin",
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
    u1 = models.User(
        username="mass_vol1",
        full_name="Mass Vol 1",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=False,
    )
    u2 = models.User(
        username="mass_vol2",
        full_name="Mass Vol 2",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    u3 = models.User(
        username="mass_lead1",
        full_name="Mass Lead 1",
        password_hash=hash_password("p"),
        role=ROLE_LEADER,
        is_active=True,
    )
    db.add_all([u1, u2, u3])
    db.commit()
    for u in [u1, u2, u3]:
        db.refresh(u)
    yield [u1, u2, u3]
    for u in [u1, u2, u3]:
        existing = db.query(models.User).filter_by(id=u.id).first()
        if existing:
            db.delete(existing)
    db.commit()


@pytest.fixture
def direction(db):
    d = models.Direction(name="Mass Action Direction")
    db.add(d)
    db.commit()
    db.refresh(d)
    yield d
    existing = db.query(models.Direction).filter_by(id=d.id).first()
    if existing:
        db.delete(existing)
    db.commit()


def test_mass_activate(client, admin_with_session, sample_users, db):
    ids = [u.id for u in sample_users[:2]]
    response = client.post("/admin/users/mass-action", data={
        "action": "activate",
        "user_ids": ids,
    }, follow_redirects=False)
    assert response.status_code == 302
    for u in sample_users[:2]:
        db.refresh(u)
        assert u.is_active is True


def test_mass_deactivate_skips_admin(client, admin_with_session, sample_users, db):
    ids = [admin_with_session.id, sample_users[1].id]
    response = client.post("/admin/users/mass-action", data={
        "action": "deactivate",
        "user_ids": ids,
    }, follow_redirects=False)
    assert response.status_code == 302
    db.refresh(admin_with_session)
    db.refresh(sample_users[1])
    assert admin_with_session.is_active is True
    assert sample_users[1].is_active is False


def test_mass_delete_skips_admin(client, admin_with_session, sample_users, db):
    admin_id = admin_with_session.id
    volunteer_id = sample_users[1].id
    ids = [admin_id, volunteer_id]
    response = client.post("/admin/users/mass-action", data={
        "action": "delete",
        "user_ids": ids,
    }, follow_redirects=False)
    assert response.status_code == 302
    db.refresh(admin_with_session)
    assert admin_with_session.is_active is True
    volunteer = db.query(models.User).filter_by(id=volunteer_id).first()
    assert volunteer is None


def test_mass_change_role_excludes_admin_target(client, admin_with_session, sample_users, db):
    ids = [admin_with_session.id, sample_users[1].id]
    response = client.post("/admin/users/mass-action", data={
        "action": "change_role",
        "user_ids": ids,
        "new_role": "lotos",
    }, follow_redirects=False)
    assert response.status_code == 302
    db.refresh(admin_with_session)
    db.refresh(sample_users[1])
    assert admin_with_session.role == ROLE_ADMIN
    assert sample_users[1].role == ROLE_LOTOS


def test_mass_change_role_to_admin_is_ignored(client, admin_with_session, sample_users, db):
    ids = [sample_users[1].id]
    response = client.post("/admin/users/mass-action", data={
        "action": "change_role",
        "user_ids": ids,
        "new_role": "admin",
    }, follow_redirects=False)
    assert response.status_code == 302
    db.refresh(sample_users[1])
    assert sample_users[1].role == ROLE_VOLUNTEER


def test_mass_add_to_direction_leader(client, admin_with_session, sample_users, direction, db):
    leader = sample_users[2]
    leader_id = leader.id
    direction_id = direction.id
    ids = [leader_id]
    response = client.post("/admin/users/mass-action", data={
        "action": "add_to_direction",
        "user_ids": ids,
        "direction_id": direction_id,
    }, follow_redirects=False)
    assert response.status_code == 302
    link = db.query(models.DirectionLeader).filter_by(
        direction_id=direction_id, user_id=leader_id
    ).first()
    assert link is not None


def test_mass_add_to_direction_volunteer(client, admin_with_session, sample_users, direction, db):
    volunteer = sample_users[1]
    volunteer_id = volunteer.id
    direction_id = direction.id
    ids = [volunteer_id]
    response = client.post("/admin/users/mass-action", data={
        "action": "add_to_direction",
        "user_ids": ids,
        "direction_id": direction_id,
    }, follow_redirects=False)
    assert response.status_code == 302
    pref = db.query(models.UserPreference).filter_by(
        direction_id=direction_id, user_id=volunteer_id
    ).first()
    assert pref is not None


def test_mass_add_to_direction_duplicate_is_ignored(client, admin_with_session, sample_users, direction, db):
    volunteer = sample_users[1]
    volunteer_id = volunteer.id
    direction_id = direction.id
    ids = [volunteer_id]
    data = {
        "action": "add_to_direction",
        "user_ids": ids,
        "direction_id": direction_id,
    }
    response1 = client.post("/admin/users/mass-action", data=data, follow_redirects=False)
    assert response1.status_code == 302
    response2 = client.post("/admin/users/mass-action", data=data, follow_redirects=False)
    assert response2.status_code == 302
    count = db.query(models.UserPreference).filter_by(
        direction_id=direction_id, user_id=volunteer_id
    ).count()
    assert count == 1


def test_mass_remove_from_direction_leader(client, admin_with_session, sample_users, direction, db):
    leader = sample_users[2]
    leader_id = leader.id
    direction_id = direction.id
    db.add(models.DirectionLeader(direction_id=direction_id, user_id=leader_id))
    db.commit()
    ids = [leader_id]
    response = client.post("/admin/users/mass-action", data={
        "action": "remove_from_direction",
        "user_ids": ids,
        "direction_id": direction_id,
    }, follow_redirects=False)
    assert response.status_code == 302
    link = db.query(models.DirectionLeader).filter_by(
        direction_id=direction_id, user_id=leader_id
    ).first()
    assert link is None


def test_mass_remove_from_direction_volunteer(client, admin_with_session, sample_users, direction, db):
    volunteer = sample_users[1]
    volunteer_id = volunteer.id
    direction_id = direction.id
    db.add(models.UserPreference(direction_id=direction_id, user_id=volunteer_id))
    db.commit()
    ids = [volunteer_id]
    response = client.post("/admin/users/mass-action", data={
        "action": "remove_from_direction",
        "user_ids": ids,
        "direction_id": direction_id,
    }, follow_redirects=False)
    assert response.status_code == 302
    pref = db.query(models.UserPreference).filter_by(
        direction_id=direction_id, user_id=volunteer_id
    ).first()
    assert pref is None


def test_mass_action_rejects_non_admin(client, sample_users, db):
    volunteer = models.User(
        username="mass_vol_nonadmin",
        full_name="Mass Nonadmin",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(volunteer)
    db.commit()
    db.refresh(volunteer)
    client.cookies.set(COOKIE_NAME, sign_cookie(volunteer.id))
    try:
        ids = [u.id for u in sample_users]
        response = client.post("/admin/users/mass-action", data={
            "action": "activate",
            "user_ids": ids,
        }, follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers.get("location") in ("/", "/login")
        for u in sample_users:
            db.refresh(u)
        assert sample_users[0].is_active is False
        assert sample_users[1].is_active is True
        assert sample_users[2].is_active is True
    finally:
        existing = db.query(models.User).filter_by(id=volunteer.id).first()
        if existing:
            db.delete(existing)
        db.commit()


def test_mass_action_empty_user_ids(client, admin_with_session, sample_users, db):
    response = client.post("/admin/users/mass-action", data={
        "action": "activate",
    }, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers.get("location", "")
    assert location.startswith("/admin")
    assert "toast_type=error" in location
    db.refresh(sample_users[0])
    db.refresh(sample_users[1])
    assert sample_users[0].is_active is False
    assert sample_users[1].is_active is True


def test_mass_action_unsupported_action(client, admin_with_session, sample_users, db):
    target = sample_users[1]
    original_role = target.role
    original_active = target.is_active
    response = client.post("/admin/users/mass-action", data={
        "action": "unknown_action",
        "user_ids": [target.id],
    }, follow_redirects=False)
    assert response.status_code == 302
    db.refresh(target)
    assert target.role == original_role
    assert target.is_active == original_active


def test_admin_page_has_filter_and_mass_action_controls(client, admin_with_session):
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.text
    assert 'id="filter-role"' in html
    assert 'id="filter-status"' in html
    assert 'id="filter-direction"' in html
    assert 'id="mass-new-role"' in html
    assert 'id="mass-direction"' in html
    assert 'data-role=' in html
    assert 'data-status=' in html
    assert 'data-directions=' in html

