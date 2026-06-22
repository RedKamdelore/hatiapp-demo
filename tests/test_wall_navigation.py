import pytest
from services.auth import hash_password, sign_cookie
from config import COOKIE_NAME
import models


@pytest.fixture
def volunteer_user_nav(db):
    user = models.User(username="vol_nav", password_hash=hash_password("vol"), role="volunteer", is_active=True)
    db.add(user); db.commit(); db.refresh(user)
    yield user
    db.delete(user); db.commit()


@pytest.fixture
def leader_user_nav(db):
    user = models.User(username="leader_nav", password_hash=hash_password("leader"), role="leader", is_active=True)
    db.add(user); db.commit(); db.refresh(user)
    yield user
    db.delete(user); db.commit()


@pytest.fixture
def lotos_user_nav(db):
    user = models.User(username="lotos_nav", password_hash=hash_password("lotos"), role="lotos", is_active=True)
    db.add(user); db.commit(); db.refresh(user)
    yield user
    db.delete(user); db.commit()


@pytest.fixture
def admin_user_nav(db):
    user = models.User(username="admin_nav", password_hash=hash_password("admin"), role="admin", is_active=True)
    db.add(user); db.commit(); db.refresh(user)
    yield user
    db.delete(user); db.commit()


def _has_wall_link(text):
    return 'href="/announcements"' in text and "Стена" in text


def test_wall_link_for_volunteer(client, volunteer_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(volunteer_user_nav.id))
    res = client.get("/schedule")
    assert res.status_code == 200
    assert _has_wall_link(res.text)


def test_wall_link_for_leader(client, leader_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(leader_user_nav.id))
    res = client.get("/leader")
    assert res.status_code == 200
    assert _has_wall_link(res.text)


def test_wall_link_for_lotos(client, lotos_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(lotos_user_nav.id))
    res = client.get("/schedule")
    assert res.status_code == 200
    assert _has_wall_link(res.text)


def test_wall_link_for_admin(client, admin_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_user_nav.id))
    res = client.get("/admin")
    assert res.status_code == 200
    assert _has_wall_link(res.text)


def test_wall_link_active_on_feed(client, volunteer_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(volunteer_user_nav.id))
    res = client.get("/announcements")
    assert res.status_code == 200
    assert 'href="/announcements" class="nav-item active"' in res.text


def test_wall_link_active_on_post_page(client, volunteer_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(volunteer_user_nav.id))
    post = client.post("/api/announcements", data={"content": "x"}).json()
    res = client.get(f"/a/{post['id']}")
    assert res.status_code == 200
    assert 'href="/announcements" class="nav-item active"' in res.text


def test_wall_icon_is_wall_brick(client, volunteer_user_nav):
    client.cookies.set(COOKIE_NAME, sign_cookie(volunteer_user_nav.id))
    res = client.get("/announcements")
    assert res.status_code == 200
    # Brick wall icon path: two vertical lines + two horizontal rectangles
    assert "M3.75 21h16.5" in res.text
    assert "M9 6.75h6v4.5H9" in res.text
