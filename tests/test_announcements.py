import pytest
from io import BytesIO

import models
from services.auth import hash_password, sign_cookie
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_VOLUNTEER, COOKIE_NAME


def _set_session(client, user):
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))


@pytest.fixture
def volunteer_user(db):
    user = models.User(
        username="volunteer_ann",
        full_name="Volunteer",
        password_hash=hash_password("vol"),
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
def leader_user(db):
    user = models.User(
        username="leader_ann",
        full_name="Leader",
        password_hash=hash_password("leader"),
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
def admin_user_ann(db):
    user = models.User(
        username="admin_ann",
        full_name="Admin",
        password_hash=hash_password("admin"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_create_announcement(client, volunteer_user):
    _set_session(client, volunteer_user)
    res = client.post("/api/announcements", data={"content": "Hello world"})
    assert res.status_code == 200
    data = res.json()
    assert data["content"] == "Hello world"
    assert data["author"]["username"] == "volunteer_ann"


def test_create_announcement_with_title(client, volunteer_user):
    _set_session(client, volunteer_user)
    res = client.post("/api/announcements", data={"title": "Important", "content": "Body"})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Important"
    assert data["content"] == "Body"


def test_list_announcements(client, volunteer_user):
    _set_session(client, volunteer_user)
    client.post("/api/announcements", data={"content": "First unique"})
    client.post("/api/announcements", data={"content": "Second unique"})
    res = client.get("/api/announcements?limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()
    contents = [p["content"] for p in data["posts"]]
    assert "First unique" in contents
    assert "Second unique" in contents


def test_feed_pagination(client, admin_user_ann):
    _set_session(client, admin_user_ann)
    for i in range(5):
        client.post("/api/announcements", data={"content": f"Pagination post {i}"})
    res = client.get("/api/announcements?limit=2&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert len(data["posts"]) == 2


def test_get_single_post(client, volunteer_user):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"title": "Title", "content": "Body"}).json()
    res = client.get(f"/api/announcements/{post['id']}")
    assert res.status_code == 200
    assert res.json()["title"] == "Title"


def test_single_post_page(client, volunteer_user):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"title": "Title", "content": "Body"}).json()
    res = client.get(f"/a/{post['id']}")
    assert res.status_code == 200
    assert "Title" in res.text
    assert "Body" in res.text


def test_edit_announcement_by_author(client, volunteer_user):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"content": "Original"}).json()
    res = client.put(f"/api/announcements/{post['id']}", data={"content": "Updated"})
    assert res.status_code == 200
    assert res.json()["content"] == "Updated"


def test_edit_announcement_by_moderator(client, volunteer_user, admin_user_ann):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"content": "Original"}).json()
    _set_session(client, admin_user_ann)
    res = client.put(f"/api/announcements/{post['id']}", data={"content": "Admin edit"})
    assert res.status_code == 200
    assert res.json()["content"] == "Admin edit"


def test_edit_announcement_by_other_fails(client, admin_user_ann, volunteer_user):
    _set_session(client, admin_user_ann)
    post = client.post("/api/announcements", data={"content": "Admin post"}).json()
    _set_session(client, volunteer_user)
    res = client.put(f"/api/announcements/{post['id']}", data={"content": "Hacked"}, follow_redirects=False)
    assert res.status_code in (302, 307, 403)
    # Verify post unchanged
    _set_session(client, admin_user_ann)
    assert client.get(f"/api/announcements/{post['id']}").json()["content"] == "Admin post"


def test_delete_announcement(client, volunteer_user):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"content": "Delete me"}).json()
    res = client.delete(f"/api/announcements/{post['id']}")
    assert res.status_code == 200
    get_res = client.get(f"/api/announcements/{post['id']}", follow_redirects=False)
    assert get_res.status_code in (302, 307, 404)


def test_pin_unpin_authorized(client, admin_user_ann, volunteer_user):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"content": "Post"}).json()
    _set_session(client, admin_user_ann)
    res = client.post(f"/api/announcements/{post['id']}/pin")
    assert res.status_code == 200
    assert res.json()["is_pinned"] is True
    res2 = client.post(f"/api/announcements/{post['id']}/pin")
    assert res2.json()["is_pinned"] is False


def test_pin_unpin_unauthorized_fails(client, admin_user_ann, volunteer_user):
    _set_session(client, admin_user_ann)
    post = client.post("/api/announcements", data={"content": "Post"}).json()
    _set_session(client, volunteer_user)
    res = client.post(f"/api/announcements/{post['id']}/pin", follow_redirects=False)
    assert res.status_code in (302, 307, 403)


def test_max_three_pinned(client, admin_user_ann):
    _set_session(client, admin_user_ann)
    for i in range(3):
        client.post("/api/announcements", data={"content": f"Post {i}", "is_pinned": "true"})
    fourth = client.post("/api/announcements", data={"content": "Fourth"}).json()
    res = client.post(f"/api/announcements/{fourth['id']}/pin")
    assert res.status_code == 400


def test_pinned_posts_appear_first(client, admin_user_ann):
    _set_session(client, admin_user_ann)
    regular = client.post("/api/announcements", data={"content": "Regular unique"}).json()
    pinned = client.post("/api/announcements", data={"content": "Pinned unique", "is_pinned": "true"}).json()
    res = client.get("/api/announcements")
    assert res.status_code == 200
    data = res.json()
    pinned_ids = [p["id"] for p in data["pinned"]]
    post_ids = [p["id"] for p in data["posts"]]
    assert pinned["id"] in pinned_ids
    assert regular["id"] in post_ids
    assert pinned["id"] not in post_ids


def test_leader_can_pin(client, leader_user, volunteer_user):
    _set_session(client, volunteer_user)
    post = client.post("/api/announcements", data={"content": "Post"}).json()
    _set_session(client, leader_user)
    res = client.post(f"/api/announcements/{post['id']}/pin")
    assert res.status_code == 200


def test_image_attachment(client, admin_user_ann):
    _set_session(client, admin_user_ann)
    img = BytesIO(b"fake image data")
    res = client.post(
        "/api/announcements",
        data={"content": "With image"},
        files={"files": ("image.png", img, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["attachments"]) == 1
    assert data["attachments"][0]["type"] == "image"


def test_invalid_attachment_rejected(client, admin_user_ann):
    _set_session(client, admin_user_ann)
    f = BytesIO(b"not an image")
    res = client.post(
        "/api/announcements",
        data={"content": "Bad file"},
        files={"files": ("file.exe", f, "application/octet-stream")},
    )
    assert res.status_code == 400


def test_unauthorized_access_redirects(client):
    res = client.get("/announcements", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "/" in res.headers.get("location", "")

