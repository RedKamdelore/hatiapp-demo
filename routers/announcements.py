from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
import uuid
import json
import re

import models
from database import get_db
from services.auth import get_current_user
from services.sse_manager import sse_manager
from config import BASE_DIR, ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS


router = APIRouter(tags=["announcements"])
api_router = APIRouter(prefix="/api/announcements", tags=["announcements"])
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "announcements"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
ALLOWED_TYPES = IMAGE_TYPES | VIDEO_TYPES
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024


def _can_moderate(user: models.User, post: models.Announcement) -> bool:
    if user.id == post.author_id:
        return True
    return user.role in {"admin", "lotos", "leader"}


def _can_pin(user: models.User) -> bool:
    return user.role in {"admin", "lotos", "leader"}


def _serialize_post(post: models.Announcement, db: Session, current_user_id: Optional[int] = None) -> dict:
    data = {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "is_pinned": post.is_pinned,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "author": {
            "id": post.author.id,
            "username": post.author.username,
            "full_name": post.author.full_name,
            "avatar": post.author.avatar,
        },
        "attachments": [
            {"id": a.id, "url": a.file_path, "type": a.file_type}
            for a in post.attachments
        ],
        "reactions": _serialize_reactions(db, post, current_user_id),
    }
    if post.poll:
        data["poll"] = _serialize_poll(post.poll, db, current_user_id)
    return data


def _serialize_poll(poll: models.AnnouncementPoll, db: Session, current_user_id: Optional[int] = None) -> dict:
    total_voters = db.query(models.PollVote.user_id).filter_by(poll_id=poll.id).distinct().count()
    option_ids = [opt.id for opt in poll.options]
    counts = {}
    if option_ids:
        rows = db.query(models.PollVote.option_id, func.count(models.PollVote.id)).filter(
            models.PollVote.option_id.in_(option_ids)
        ).group_by(models.PollVote.option_id).all()
        counts = {row[0]: row[1] for row in rows}

    voters_by_option = {}
    text_voters = []
    if not poll.is_anonymous:
        for opt in poll.options:
            votes = (
                db.query(models.PollVote)
                .options(joinedload(models.PollVote.user))
                .filter_by(poll_id=poll.id, option_id=opt.id)
                .order_by(models.PollVote.created_at.desc())
                .all()
            )
            voters_by_option[opt.id] = [_serialize_poll_voter(v.user) for v in votes]
        if poll.poll_type == "text":
            text_votes = (
                db.query(models.PollVote)
                .options(joinedload(models.PollVote.user))
                .filter_by(poll_id=poll.id)
                .filter(models.PollVote.text_answer.isnot(None))
                .order_by(models.PollVote.created_at.desc())
                .all()
            )
            text_voters = [
                {"user": _serialize_poll_voter(v.user), "text_answer": v.text_answer}
                for v in text_votes
            ]

    options = []
    for opt in poll.options:
        options.append({
            "id": opt.id,
            "label": opt.label,
            "sort_order": opt.sort_order,
            "votes": counts.get(opt.id, 0),
            "voters": voters_by_option.get(opt.id, []),
        })
    user_votes = []
    text_answer = None
    if current_user_id:
        user_votes_rows = db.query(models.PollVote).filter_by(poll_id=poll.id, user_id=current_user_id).all()
        user_votes = [v.option_id for v in user_votes_rows if v.option_id]
        text_votes = [v.text_answer for v in user_votes_rows if v.text_answer]
        if text_votes:
            text_answer = text_votes[0]
    return {
        "id": poll.id,
        "question": poll.question,
        "poll_type": poll.poll_type,
        "is_anonymous": poll.is_anonymous,
        "options": options,
        "total_voters": total_voters,
        "user_votes": user_votes,
        "text_answer": text_answer,
        "text_voters": text_voters,
    }


REACTION_TYPES = {"like", "love", "laugh", "wow", "sad", "fire"}
REACTION_LABELS = {
    "like": "👍",
    "love": "❤️",
    "laugh": "😂",
    "wow": "😮",
    "sad": "😢",
    "fire": "🔥",
}


def _serialize_reactions(db: Session, post: models.Announcement, current_user_id: Optional[int] = None) -> dict:
    counts = {}
    for r in db.query(models.AnnouncementReaction).filter_by(announcement_id=post.id).all():
        counts[r.reaction] = counts.get(r.reaction, 0) + 1
    user_reactions = set()
    if current_user_id:
        user_reactions = {
            r.reaction
            for r in db.query(models.AnnouncementReaction).filter_by(announcement_id=post.id, user_id=current_user_id).all()
        }
    return {
        "counts": {k: counts.get(k, 0) for k in REACTION_TYPES},
        "user_reactions": list(user_reactions),
    }


def _serialize_poll_voter(user: models.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "avatar": user.avatar,
        "role": user.role,
    }


async def _save_attachments(files: List[UploadFile], post_id: int, db: Session):
    for file in files:
        if not file or not file.filename:
            continue
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Недопустимый тип файла: {content_type}")

        file_bytes = await file.read()
        if content_type in IMAGE_TYPES and len(file_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Изображение слишком большое (максимум 100 МБ)")
        if content_type in VIDEO_TYPES and len(file_bytes) > MAX_VIDEO_BYTES:
            raise HTTPException(status_code=400, detail="Видео слишком большое (максимум 2 ГБ)")

        ext = Path(file.filename).suffix.lower() or ".bin"
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        attachment = models.AnnouncementAttachment(
            announcement_id=post_id,
            file_path=f"/static/uploads/announcements/{filename}",
            file_type="image" if content_type in IMAGE_TYPES else "video",
        )
        db.add(attachment)


@api_router.post("")
async def create_announcement(
    request: Request,
    title: Optional[str] = Form(None),
    content: str = Form(...),
    is_pinned: bool = Form(False),
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)

    if is_pinned and not _can_pin(user):
        raise HTTPException(status_code=403, detail="Нет прав для закрепления")

    if is_pinned:
        pinned_count = db.query(models.Announcement).filter_by(is_pinned=True).count()
        if pinned_count >= 3:
            raise HTTPException(status_code=400, detail="Максимум 3 закреплённых поста")

    post = models.Announcement(
        author_id=user.id,
        title=title.strip() if title else None,
        content=content.strip(),
        is_pinned=is_pinned,
    )
    db.add(post)
    db.flush()

    await _save_attachments(files, post.id, db)

    db.commit()
    db.refresh(post)

    await sse_manager.broadcast({
        "type": "announcement",
        "post_id": post.id,
        "title": post.title,
        "author_name": post.author.full_name or post.author.username,
    })

    return _serialize_post(post, db)


@api_router.get("")
def list_announcements(
    request: Request,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    pinned = (
        db.query(models.Announcement)
        .options(
            joinedload(models.Announcement.author),
            joinedload(models.Announcement.attachments),
            joinedload(models.Announcement.poll).joinedload(models.AnnouncementPoll.options),
        )
        .filter_by(is_pinned=True)
        .order_by(models.Announcement.created_at.desc())
        .all()
    )
    regular = (
        db.query(models.Announcement)
        .options(
            joinedload(models.Announcement.author),
            joinedload(models.Announcement.attachments),
            joinedload(models.Announcement.poll).joinedload(models.AnnouncementPoll.options),
        )
        .filter_by(is_pinned=False)
        .order_by(models.Announcement.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return {
        "pinned": [_serialize_post(p, db, user.id) for p in pinned],
        "posts": [_serialize_post(p, db, user.id) for p in regular],
        "limit": limit,
        "offset": offset,
    }


@api_router.get("/{post_id}/comments")
def list_comments(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    comments = (
        db.query(models.AnnouncementComment)
        .options(joinedload(models.AnnouncementComment.author))
        .filter_by(announcement_id=post_id)
        .order_by(models.AnnouncementComment.created_at.asc())
        .all()
    )
    return {"comments": [_serialize_comment(c) for c in comments]}


@api_router.post("/{post_id}/comments")
async def create_comment(
    request: Request,
    post_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")

    comment = models.AnnouncementComment(
        announcement_id=post_id,
        author_id=user.id,
        content=content.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    if post.author_id != user.id:
        await sse_manager.send_to_user(post.author_id, {
            "type": "comment",
            "post_id": post.id,
            "post_title": post.title,
            "comment_id": comment.id,
            "author_name": user.full_name or user.username,
        })

    return _serialize_comment(comment)


@api_router.put("/{post_id}/comments/{comment_id}")
def update_comment(
    request: Request,
    post_id: int,
    comment_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    comment = (
        db.query(models.AnnouncementComment)
        .options(joinedload(models.AnnouncementComment.author))
        .filter_by(id=comment_id, announcement_id=post_id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Комментарий не найден")
    if not _can_moderate_comment(user, comment):
        raise HTTPException(status_code=403, detail="Нет доступа")

    comment.content = content.strip()
    comment.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment)


@api_router.delete("/{post_id}/comments/{comment_id}")
def delete_comment(
    request: Request,
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    comment = (
        db.query(models.AnnouncementComment)
        .filter_by(id=comment_id, announcement_id=post_id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Комментарий не найден")
    if not _can_moderate_comment(user, comment):
        raise HTTPException(status_code=403, detail="Нет доступа")

    db.delete(comment)
    db.commit()
    return {"ok": True}


@api_router.get("/{post_id}")
def get_announcement(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = (
        db.query(models.Announcement)
        .options(
            joinedload(models.Announcement.author),
            joinedload(models.Announcement.attachments),
            joinedload(models.Announcement.poll).joinedload(models.AnnouncementPoll.options),
        )
        .filter_by(id=post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    return _serialize_post(post, db, user.id)


@api_router.put("/{post_id}")
async def update_announcement(
    request: Request,
    post_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    is_pinned: Optional[bool] = Form(None),
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    if not _can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")

    if content is not None:
        post.content = content.strip()
    if title is not None:
        post.title = title.strip() or None

    if is_pinned is not None and is_pinned != post.is_pinned:
        if not _can_pin(user):
            raise HTTPException(status_code=403, detail="Нет прав для закрепления")
        if is_pinned:
            pinned_count = db.query(models.Announcement).filter_by(is_pinned=True).count()
            if pinned_count >= 3:
                raise HTTPException(status_code=400, detail="Максимум 3 закреплённых поста")
        post.is_pinned = is_pinned

    post.updated_at = datetime.now(timezone.utc)

    await _save_attachments(files, post.id, db)

    db.commit()
    db.refresh(post)
    return _serialize_post(post, db, user.id)


@api_router.delete("/{post_id}")
def delete_announcement(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.attachments))
        .filter_by(id=post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    if not _can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")

    for attachment in post.attachments:
        try:
            (BASE_DIR / attachment.file_path.lstrip("/")).unlink(missing_ok=True)
        except Exception:
            pass

    db.delete(post)
    db.commit()
    return {"ok": True}


def _parse_poll_options(options_json: Optional[str]) -> List[str]:
    if not options_json:
        return []
    try:
        data = json.loads(options_json)
        if isinstance(data, list):
            return [str(o).strip() for o in data if str(o).strip()]
    except json.JSONDecodeError:
        pass
    return [o.strip() for o in options_json.split('\n') if o.strip()]


def _can_edit_poll(poll: models.AnnouncementPoll, db: Session) -> bool:
    return db.query(models.PollVote).filter_by(poll_id=poll.id).first() is None


@api_router.get("/{post_id}/poll")
def get_poll(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    poll = (
        db.query(models.AnnouncementPoll)
        .options(joinedload(models.AnnouncementPoll.options))
        .filter_by(announcement_id=post_id)
        .first()
    )
    if not poll:
        raise HTTPException(status_code=404, detail="Опрос не найден")
    return _serialize_poll(poll, db, user.id)


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).lower() in {"true", "1", "yes", "on"}


@api_router.post("/{post_id}/poll")
def create_poll(
    request: Request,
    post_id: int,
    question: str = Form(...),
    poll_type: str = Form(...),
    options: Optional[str] = Form(None),
    is_anonymous: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    if post.author_id != user.id and not _can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if post.poll:
        raise HTTPException(status_code=400, detail="Опрос уже существует")

    poll_type = poll_type.lower()
    if poll_type not in {"single", "multiple", "text"}:
        raise HTTPException(status_code=400, detail="Неверный тип опроса")

    option_labels = _parse_poll_options(options)
    if poll_type in {"single", "multiple"} and len(option_labels) < 2:
        raise HTTPException(status_code=400, detail="Минимум 2 варианта")
    if poll_type == "text":
        option_labels = []

    poll = models.AnnouncementPoll(
        announcement_id=post_id,
        question=question.strip(),
        poll_type=poll_type,
        is_anonymous=_parse_bool(is_anonymous),
    )
    db.add(poll)
    db.flush()

    for idx, label in enumerate(option_labels):
        db.add(models.PollOption(poll_id=poll.id, label=label, sort_order=idx))

    db.commit()
    db.refresh(poll)
    return _serialize_poll(poll, db, user.id)


@api_router.put("/{post_id}/poll")
def update_poll(
    request: Request,
    post_id: int,
    question: Optional[str] = Form(None),
    poll_type: Optional[str] = Form(None),
    options: Optional[str] = Form(None),
    is_anonymous: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    poll = post.poll
    if not poll:
        raise HTTPException(status_code=404, detail="Опрос не найден")
    if post.author_id != user.id and not _can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if not _can_edit_poll(poll, db):
        raise HTTPException(status_code=400, detail="Нельзя редактировать опрос после первого голоса")

    if question is not None:
        poll.question = question.strip()
    if poll_type is not None:
        poll_type = poll_type.lower()
        if poll_type not in {"single", "multiple", "text"}:
            raise HTTPException(status_code=400, detail="Неверный тип опроса")
        poll.poll_type = poll_type
    if is_anonymous is not None:
        poll.is_anonymous = _parse_bool(is_anonymous)

    new_type = poll.poll_type
    option_labels = _parse_poll_options(options)
    if new_type in {"single", "multiple"}:
        if options is not None and len(option_labels) < 2:
            raise HTTPException(status_code=400, detail="Минимум 2 варианта")
        if options is not None:
            db.query(models.PollOption).filter_by(poll_id=poll.id).delete()
            for idx, label in enumerate(option_labels):
                db.add(models.PollOption(poll_id=poll.id, label=label, sort_order=idx))
    elif new_type == "text":
        db.query(models.PollOption).filter_by(poll_id=poll.id).delete()

    poll.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(poll)
    return _serialize_poll(poll, db, user.id)


@api_router.delete("/{post_id}/poll")
def delete_poll(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    poll = post.poll
    if not poll:
        raise HTTPException(status_code=404, detail="Опрос не найден")
    if post.author_id != user.id and not _can_moderate(user, post):
        raise HTTPException(status_code=403, detail="Нет доступа")

    db.delete(poll)
    db.commit()
    return {"ok": True}


@api_router.post("/{post_id}/poll/vote")
def vote_poll(
    request: Request,
    post_id: int,
    option_ids: Optional[str] = Form(None),
    text_answer: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    poll = post.poll
    if not poll:
        raise HTTPException(status_code=404, detail="Опрос не найден")

    if poll.poll_type == "text":
        if not text_answer or not text_answer.strip():
            raise HTTPException(status_code=400, detail="Введите ответ")
        db.query(models.PollVote).filter_by(poll_id=poll.id, user_id=user.id).delete()
        vote = models.PollVote(
            poll_id=poll.id,
            user_id=user.id,
            text_answer=text_answer.strip(),
        )
        db.add(vote)
        db.commit()
        db.refresh(poll)
        return _serialize_poll(poll, db, user.id)

    selected = []
    if option_ids:
        try:
            data = json.loads(option_ids)
            selected = [int(x) for x in (data if isinstance(data, list) else [data])]
        except (json.JSONDecodeError, ValueError):
            selected = [int(x) for x in option_ids.split(",") if x.strip().isdigit()]

    if poll.poll_type == "single" and len(selected) != 1:
        raise HTTPException(status_code=400, detail="Выберите один вариант")
    if poll.poll_type == "multiple" and not selected:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один вариант")

    valid_option_ids = {opt.id for opt in poll.options}
    if any(opt_id not in valid_option_ids for opt_id in selected):
        raise HTTPException(status_code=400, detail="Неверный вариант")

    db.query(models.PollVote).filter_by(poll_id=poll.id, user_id=user.id).delete()
    for opt_id in selected:
        db.add(models.PollVote(poll_id=poll.id, option_id=opt_id, user_id=user.id))
    db.commit()
    db.refresh(poll)
    return _serialize_poll(poll, db, user.id)


@api_router.delete("/{post_id}/poll/vote")
def delete_own_vote(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    poll = post.poll
    if not poll:
        raise HTTPException(status_code=404, detail="Опрос не найден")

    db.query(models.PollVote).filter_by(poll_id=poll.id, user_id=user.id).delete()
    db.commit()
    db.refresh(poll)
    return _serialize_poll(poll, db, user.id)


@api_router.get("/{post_id}/poll/voters")
def list_poll_voters(
    request: Request,
    post_id: int,
    option_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    poll = post.poll
    if not poll:
        raise HTTPException(status_code=404, detail="Опрос не найден")

    if poll.is_anonymous:
        raise HTTPException(status_code=400, detail="Голоса анонимные")

    query = db.query(models.PollVote).options(joinedload(models.PollVote.user)).filter_by(poll_id=poll.id)
    if poll.poll_type == "text":
        votes = query.filter(models.PollVote.text_answer.isnot(None)).order_by(models.PollVote.created_at.desc()).all()
        return {
            "voters": [
                {
                    "user": {
                        "id": v.user.id,
                        "username": v.user.username,
                        "full_name": v.user.full_name,
                        "avatar": v.user.avatar,
                        "role": v.user.role,
                    },
                    "text_answer": v.text_answer,
                }
                for v in votes
            ]
        }

    if option_id is None:
        raise HTTPException(status_code=400, detail="Укажите option_id")
    option = db.query(models.PollOption).filter_by(id=option_id, poll_id=poll.id).first()
    if not option:
        raise HTTPException(status_code=404, detail="Вариант не найден")

    votes = query.filter_by(option_id=option_id).order_by(models.PollVote.created_at.desc()).all()
    return {
        "voters": [
            {
                "id": v.user.id,
                "username": v.user.username,
                "full_name": v.user.full_name,
                "avatar": v.user.avatar,
                "role": v.user.role,
            }
            for v in votes
        ]
    }


@api_router.post("/{post_id}/pin")
def pin_announcement(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not _can_pin(user):
        raise HTTPException(status_code=403, detail="Нет прав")

    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")

    new_state = not post.is_pinned
    if new_state:
        pinned_count = db.query(models.Announcement).filter_by(is_pinned=True).count()
        if pinned_count >= 3:
            raise HTTPException(status_code=400, detail="Максимум 3 закреплённых поста")

    post.is_pinned = new_state
    post.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(post)
    return _serialize_post(post, db, user.id)


@api_router.post("/{post_id}/reactions")
def add_reaction(
    request: Request,
    post_id: int,
    reaction: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if reaction not in REACTION_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестная реакция")
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    existing = db.query(models.AnnouncementReaction).filter_by(
        announcement_id=post_id, user_id=user.id, reaction=reaction
    ).first()
    if existing:
        return _serialize_post(post, db, user.id)
    db.add(models.AnnouncementReaction(
        announcement_id=post_id,
        user_id=user.id,
        reaction=reaction,
    ))
    db.commit()
    db.refresh(post)
    return _serialize_post(post, db, user.id)


@api_router.delete("/{post_id}/reactions/{reaction}")
def remove_reaction(
    request: Request,
    post_id: int,
    reaction: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if reaction not in REACTION_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестная реакция")
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    existing = db.query(models.AnnouncementReaction).filter_by(
        announcement_id=post_id, user_id=user.id, reaction=reaction
    ).first()
    if not existing:
        return _serialize_post(post, db, user.id)
    db.delete(existing)
    db.commit()
    db.refresh(post)
    return _serialize_post(post, db, user.id)


@api_router.get("/{post_id}/reactions/{reaction}")
def list_reaction_users(
    request: Request,
    post_id: int,
    reaction: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if reaction not in REACTION_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестная реакция")
    post = db.query(models.Announcement).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    rows = (
        db.query(models.AnnouncementReaction)
        .options(joinedload(models.AnnouncementReaction.user))
        .filter_by(announcement_id=post_id, reaction=reaction)
        .order_by(models.AnnouncementReaction.created_at.desc())
        .all()
    )
    return {
        "reaction": reaction,
        "label": REACTION_LABELS[reaction],
        "users": [
            {
                "id": r.user.id,
                "username": r.user.username,
                "full_name": r.user.full_name,
                "avatar": r.user.avatar,
                "role": r.user.role,
            }
            for r in rows
        ],
    }


def _can_moderate_comment(user: models.User, comment: models.AnnouncementComment) -> bool:
    if user.id == comment.author_id:
        return True
    return user.role in {ROLE_ADMIN, ROLE_LOTOS, ROLE_LEADER}


def _serialize_comment(comment: models.AnnouncementComment) -> dict:
    return {
        "id": comment.id,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
        "author": {
            "id": comment.author.id,
            "username": comment.author.username,
            "full_name": comment.author.full_name,
            "avatar": comment.author.avatar,
            "role": comment.author.role,
        },
    }


@router.get("/announcements", response_class=HTMLResponse)
def announcements_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(request, "announcements.html", {
        "request": request,
        "user": user,
        "can_pin": _can_pin(user),
    })


@router.get("/a/{post_id}", response_class=HTMLResponse)
def announcement_page(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    post = (
        db.query(models.Announcement)
        .options(joinedload(models.Announcement.author), joinedload(models.Announcement.attachments), joinedload(models.Announcement.comments).joinedload(models.AnnouncementComment.author))
        .filter_by(id=post_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    return templates.TemplateResponse(request, "announcement.html", {
        "request": request,
        "user": user,
        "post": post,
        "can_edit": _can_moderate(user, post),
        "can_pin": _can_pin(user),
    })
