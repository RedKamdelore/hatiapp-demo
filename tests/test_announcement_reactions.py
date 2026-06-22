import pytest

import models
from services.auth import hash_password, sign_cookie
from config import ROLE_VOLUNTEER, COOKIE_NAME


def _set_session(client, user):
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))


@pytest.fixture
def user_a(db):
    user = models.User(
        username="react_a",
        full_name="User A",
        password_hash=hash_password("x"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


@pytest.fixture
def user_b(db):
    user = models.User(
        username="react_b",
        full_name="User B",
        password_hash=hash_password("x"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


@pytest.fixture
def post(client, user_a):
    _set_session(client, user_a)
    res = client.post("/api/announcements", data={"content": "Reactable post"})
    return res.json()


def test_add_reaction_increments_count(client, user_a, post):
    _set_session(client, user_a)
    res = client.post(f"/api/announcements/{post['id']}/reactions", data={"reaction": "like"})
    assert res.status_code == 200
    data = res.json()
    assert data["reactions"]["counts"]["like"] == 1
    assert "like" in data["reactions"]["user_reactions"]


def test_remove_reaction(client, user_a, post):
    _set_session(client, user_a)
    pid = post["id"]
    client.post(f"/api/announcements/{pid}/reactions", data={"reaction": "love"})
    res = client.delete(f"/api/announcements/{pid}/reactions/love")
    assert res.status_code == 200
    data = res.json()
    assert data["reactions"]["counts"]["love"] == 0
    assert "love" not in data["reactions"]["user_reactions"]


def test_multiple_users_and_reactions(client, user_a, user_b, post):
    pid = post["id"]
    _set_session(client, user_a)
    client.post(f"/api/announcements/{pid}/reactions", data={"reaction": "like"})
    client.post(f"/api/announcements/{pid}/reactions", data={"reaction": "fire"})
    _set_session(client, user_b)
    res = client.post(f"/api/announcements/{pid}/reactions", data={"reaction": "like"})
    data = res.json()
    assert data["reactions"]["counts"]["like"] == 2
    assert data["reactions"]["counts"]["fire"] == 1
    assert data["reactions"]["counts"]["love"] == 0


def test_unknown_reaction_rejected(client, user_a, post):
    _set_session(client, user_a)
    res = client.post(f"/api/announcements/{post['id']}/reactions", data={"reaction": "invalid"})
    assert res.status_code == 400


def test_reaction_user_list(client, user_a, user_b, post):
    pid = post["id"]
    _set_session(client, user_a)
    client.post(f"/api/announcements/{pid}/reactions", data={"reaction": "like"})
    _set_session(client, user_b)
    client.post(f"/api/announcements/{pid}/reactions", data={"reaction": "like"})
    res = client.get(f"/api/announcements/{pid}/reactions/like")
    assert res.status_code == 200
    data = res.json()
    assert data["reaction"] == "like"
    assert len(data["users"]) == 2
    ids = {u["id"] for u in data["users"]}
    assert user_a.id in ids
    assert user_b.id in ids


def test_feed_includes_reactions(client, user_a, post):
    _set_session(client, user_a)
    client.post(f"/api/announcements/{post['id']}/reactions", data={"reaction": "wow"})
    res = client.get("/api/announcements?limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()
    p = next((x for x in data["posts"] if x["id"] == post["id"]), None)
    assert p is not None
    assert p["reactions"]["counts"]["wow"] == 1
