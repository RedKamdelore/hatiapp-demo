import uuid
import pytest

from config import COOKIE_NAME
from services.auth import sign_cookie
import models


@pytest.fixture
def post_author(db, admin_user):
    return admin_user


@pytest.fixture
def announcement(db, post_author):
    post = models.Announcement(
        author_id=post_author.id,
        title="Test Post",
        content="Test content",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@pytest.fixture
def volunteer_user(db):
    from services.auth import hash_password
    username = f"volunteer_commenter_{uuid.uuid4().hex[:8]}"
    user = models.User(
        username=username,
        full_name="Volunteer Commenter",
        password_hash=hash_password("pass"),
        role="volunteer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_list_comments_empty(client, admin_with_session, announcement):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_with_session.id))
    res = client.get(f"/api/announcements/{announcement.id}/comments")
    assert res.status_code == 200
    assert res.json()["comments"] == []


def test_create_comment(client, admin_with_session, announcement):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_with_session.id))
    res = client.post(
        f"/api/announcements/{announcement.id}/comments",
        data={"content": "Nice post"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["content"] == "Nice post"
    assert data["author"]["id"] == admin_with_session.id


def test_author_can_edit_comment(client, admin_with_session, announcement, db):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_with_session.id))
    comment = models.AnnouncementComment(
        announcement_id=announcement.id,
        author_id=admin_with_session.id,
        content="Original",
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    res = client.put(
        f"/api/announcements/{announcement.id}/comments/{comment.id}",
        data={"content": "Updated"},
    )
    assert res.status_code == 200
    assert res.json()["content"] == "Updated"


def test_other_user_cannot_edit_comment(client, admin_with_session, volunteer_user, announcement, db):
    client.cookies.set(COOKIE_NAME, sign_cookie(volunteer_user.id))
    comment = models.AnnouncementComment(
        announcement_id=announcement.id,
        author_id=admin_with_session.id,
        content="Original",
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    res = client.put(
        f"/api/announcements/{announcement.id}/comments/{comment.id}",
        data={"content": "Hacked"},
    )
    assert res.status_code == 403


def test_author_can_delete_comment(client, admin_with_session, announcement, db):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_with_session.id))
    comment = models.AnnouncementComment(
        announcement_id=announcement.id,
        author_id=admin_with_session.id,
        content="To delete",
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    res = client.delete(f"/api/announcements/{announcement.id}/comments/{comment.id}")
    assert res.status_code == 200
    assert db.query(models.AnnouncementComment).filter_by(id=comment.id).first() is None


def test_leader_can_delete_any_comment(client, admin_with_session, volunteer_user, announcement, db):
    from services.auth import hash_password
    leader = models.User(
        username="leader_mod",
        full_name="Leader Moderator",
        password_hash=hash_password("pass"),
        role="leader",
        is_active=True,
    )
    db.add(leader)
    db.commit()
    db.refresh(leader)

    comment = models.AnnouncementComment(
        announcement_id=announcement.id,
        author_id=volunteer_user.id,
        content="Spam",
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    client.cookies.set(COOKIE_NAME, sign_cookie(leader.id))
    res = client.delete(f"/api/announcements/{announcement.id}/comments/{comment.id}")
    assert res.status_code == 200


def test_comments_include_author_role(client, admin_with_session, volunteer_user, announcement, db):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_with_session.id))
    comment = models.AnnouncementComment(
        announcement_id=announcement.id,
        author_id=volunteer_user.id,
        content="Hello",
    )
    db.add(comment)
    db.commit()

    res = client.get(f"/api/announcements/{announcement.id}/comments")
    assert res.status_code == 200
    authors = [c["author"] for c in res.json()["comments"]]
    assert any(a["id"] == volunteer_user.id and a["role"] == "volunteer" for a in authors)


def test_post_page_renders_comments_section(client, admin_with_session, announcement):
    client.cookies.set(COOKIE_NAME, sign_cookie(admin_with_session.id))
    res = client.get(f"/a/{announcement.id}")
    assert res.status_code == 200
    assert "comments-section" in res.text
    assert "Комментарии" in res.text
