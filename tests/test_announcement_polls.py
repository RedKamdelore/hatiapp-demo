import uuid
import json
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
        title="Poll Post",
        content="Post with a poll",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@pytest.fixture
def voter(db):
    from services.auth import hash_password
    username = f"voter_{uuid.uuid4().hex[:8]}"
    user = models.User(
        username=username,
        full_name="Voter User",
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


def _auth(client, user):
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))


def test_create_single_poll(client, admin_with_session, announcement):
    _auth(client, admin_with_session)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "Лучший цвет?",
            "poll_type": "single",
            "options": json.dumps(["Красный", "Синий"]),
            "is_anonymous": "false",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["question"] == "Лучший цвет?"
    assert data["poll_type"] == "single"
    assert len(data["options"]) == 2
    assert data["is_anonymous"] is False


def test_non_author_cannot_create_poll(client, admin_with_session, voter, announcement):
    _auth(client, voter)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    )
    assert res.status_code == 403


def test_single_vote(client, admin_with_session, voter, announcement, db):
    _auth(client, admin_with_session)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "Выберите один",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    )
    poll = res.json()
    option_id = poll["options"][0]["id"]

    _auth(client, voter)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([option_id])},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user_votes"] == [option_id]
    assert data["options"][0]["votes"] == 1
    assert data["total_voters"] == 1


def test_single_vote_requires_exactly_one(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    )
    poll = res.json()
    ids = [o["id"] for o in poll["options"]]

    _auth(client, voter)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps(ids)},
    )
    assert res.status_code == 400


def test_multiple_vote(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "Выберите несколько",
            "poll_type": "multiple",
            "options": json.dumps(["А", "Б", "В"]),
        },
    )
    poll = res.json()
    ids = [o["id"] for o in poll["options"][:2]]

    _auth(client, voter)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps(ids)},
    )
    assert res.status_code == 200
    data = res.json()
    assert set(data["user_votes"]) == set(ids)
    assert data["total_voters"] == 1


def test_text_poll(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "Ваш комментарий",
            "poll_type": "text",
        },
    )
    assert res.status_code == 200

    _auth(client, voter)
    res = client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"text_answer": "Ответ текстом"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["text_answer"] == "Ответ текстом"


def test_change_vote(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    poll = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    ).json()
    ids = [o["id"] for o in poll["options"]]

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([ids[0]])},
    )
    res = client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([ids[1]])},
    )
    data = res.json()
    assert data["user_votes"] == [ids[1]]
    assert data["options"][0]["votes"] == 0
    assert data["options"][1]["votes"] == 1


def test_delete_own_vote(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    poll = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    ).json()
    option_id = poll["options"][0]["id"]

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([option_id])},
    )
    res = client.delete(f"/api/announcements/{announcement.id}/poll/vote")
    assert res.status_code == 200
    data = res.json()
    assert data["user_votes"] == []
    assert data["options"][0]["votes"] == 0


def test_cannot_edit_poll_after_vote(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    poll = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    ).json()
    option_id = poll["options"][0]["id"]

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([option_id])},
    )

    _auth(client, admin_with_session)
    res = client.put(
        f"/api/announcements/{announcement.id}/poll",
        data={"question": "Новый вопрос"},
    )
    assert res.status_code == 400


def test_author_can_delete_poll(client, admin_with_session, announcement, db):
    _auth(client, admin_with_session)
    client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    )
    res = client.delete(f"/api/announcements/{announcement.id}/poll")
    assert res.status_code == 200
    assert db.query(models.AnnouncementPoll).filter_by(announcement_id=announcement.id).first() is None


def test_non_author_cannot_delete_poll(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    )
    _auth(client, voter)
    res = client.delete(f"/api/announcements/{announcement.id}/poll")
    assert res.status_code == 403


def test_feed_includes_poll_badge(client, admin_with_session, announcement):
    _auth(client, admin_with_session)
    client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    )
    res = client.get("/api/announcements")
    assert res.status_code == 200
    posts = res.json()["posts"]
    assert any(p["id"] == announcement.id and p["poll"] for p in posts)


def test_poll_results_include_voters(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    poll = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    ).json()
    option_id = poll["options"][0]["id"]

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([option_id])},
    )

    _auth(client, admin_with_session)
    res = client.get(f"/api/announcements/{announcement.id}/poll")
    data = res.json()
    option = next(o for o in data["options"] if o["id"] == option_id)
    assert len(option["voters"]) == 1
    assert option["voters"][0]["id"] == voter.id


def test_anonymous_poll_hides_voters(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    poll = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
            "is_anonymous": "true",
        },
    ).json()
    option_id = poll["options"][0]["id"]

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([option_id])},
    )

    _auth(client, admin_with_session)
    res = client.get(f"/api/announcements/{announcement.id}/poll")
    data = res.json()
    option = next(o for o in data["options"] if o["id"] == option_id)
    assert option["voters"] == []
    res2 = client.get(f"/api/announcements/{announcement.id}/poll/voters?option_id={option_id}")
    assert res2.status_code == 400


def test_voters_endpoint_lists_option_voters(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    poll = client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "single",
            "options": json.dumps(["А", "Б"]),
        },
    ).json()
    option_id = poll["options"][0]["id"]

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"option_ids": json.dumps([option_id])},
    )

    _auth(client, admin_with_session)
    res = client.get(f"/api/announcements/{announcement.id}/poll/voters?option_id={option_id}")
    assert res.status_code == 200
    voters = res.json()["voters"]
    assert len(voters) == 1
    assert voters[0]["id"] == voter.id


def test_text_poll_results_include_voters(client, admin_with_session, voter, announcement):
    _auth(client, admin_with_session)
    client.post(
        f"/api/announcements/{announcement.id}/poll",
        data={
            "question": "?",
            "poll_type": "text",
        },
    )

    _auth(client, voter)
    client.post(
        f"/api/announcements/{announcement.id}/poll/vote",
        data={"text_answer": "Мой ответ"},
    )

    _auth(client, admin_with_session)
    res = client.get(f"/api/announcements/{announcement.id}/poll")
    data = res.json()
    assert len(data["text_voters"]) == 1
    assert data["text_voters"][0]["user"]["id"] == voter.id
    assert data["text_voters"][0]["text_answer"] == "Мой ответ"
