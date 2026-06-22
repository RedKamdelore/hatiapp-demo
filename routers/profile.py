import uuid
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from services.auth import get_current_user, hash_password, verify_password
from services.booking import cancel_booking, cancel_booking_by_id, cancel_deadline_ok
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")
AVATAR_DIR = Path("static/avatars")


def _profile_ctx(request, user, db, error=None, success=None):
    directions = db.query(models.Direction).order_by(models.Direction.name).all()
    preferred_ids = {
        p.direction_id for p in
        db.query(models.UserPreference).filter_by(user_id=user.id).all()
    }
    return {
        "request": request,
        "user": user,
        "directions": directions,
        "preferred_ids": preferred_ids,
        "error": error,
        "success": success,
    }


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("profile.html", _profile_ctx(request, user, db))


@router.post("/profile/avatar")
async def upload_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    ext = Path(avatar.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return templates.TemplateResponse("profile.html",
            _profile_ctx(request, user, db, error="Только JPG, PNG или WEBP"))
    
    # Лимит 2MB
    MAX_AVATAR_SIZE = 2 * 1024 * 1024
    content = await avatar.read()
    if len(content) > MAX_AVATAR_SIZE:
        return templates.TemplateResponse("profile.html",
            _profile_ctx(request, user, db, error="Файл слишком большой (макс. 2 МБ)"))
    
    filename = f"{uuid.uuid4()}{ext}"
    dest = AVATAR_DIR / filename
    with dest.open("wb") as f:
        f.write(content)
    if user.avatar:
        old = AVATAR_DIR / user.avatar
        if old.exists():
            old.unlink()
    user.avatar = filename
    db.commit()
    return RedirectResponse("/profile?toast=Аватар+обновлён", status_code=302)


@router.post("/profile/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse("profile.html",
            _profile_ctx(request, user, db, error="Неверный текущий пароль"))
    if len(new_password) < 4:
        return templates.TemplateResponse("profile.html",
            _profile_ctx(request, user, db, error="Пароль должен быть минимум 4 символа"))
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/profile?toast=Пароль+изменён", status_code=302)


@router.post("/profile/name")
def change_name(
    request: Request,
    full_name: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    user.full_name = full_name.strip() or None
    db.commit()
    return RedirectResponse("/profile?toast=Имя+обновлено", status_code=302)


@router.post("/profile/preferences")
async def save_preferences(
    request: Request,
    db: Session = Depends(get_db),
):
    """Сохраняет предпочитаемые направления пользователя."""
    user = get_current_user(request, db)
    form = await request.form()
    direction_ids = [int(v) for v in form.getlist("direction_ids") if str(v).isdigit()]

    # Заменяем все предпочтения за один раз
    db.query(models.UserPreference).filter_by(user_id=user.id).delete()
    for did in direction_ids:
        # Проверяем что направление существует
        if db.query(models.Direction).filter_by(id=did).first():
            db.add(models.UserPreference(user_id=user.id, direction_id=did))
    db.commit()
    return RedirectResponse("/profile?success=preferences", status_code=302)


@router.get("/profile/@{username}", response_class=HTMLResponse)
def public_profile(username: str, request: Request, db: Session = Depends(get_db)):
    viewer = get_current_user(request, db)
    target = db.query(models.User).filter_by(username=username).first()
    if not target:
        return RedirectResponse("/schedule", status_code=302)
    return _render_public_profile(request, db, viewer, target)


@router.get("/profile/{user_id:int}", response_class=HTMLResponse)
def public_profile_by_id(user_id: int, request: Request, db: Session = Depends(get_db)):
    viewer = get_current_user(request, db)
    target = db.query(models.User).filter_by(id=user_id).first()
    if not target:
        return RedirectResponse("/schedule", status_code=302)
    return _render_public_profile(request, db, viewer, target)


def _render_public_profile(request, db, viewer, target):
    # Для точного 24h-чека в шаблоне
    cancel_cutoff = datetime.now() + timedelta(hours=24)

    # Права на отмену смен:
    # admin/leader/lotos — могут отменять любому (без дедлайна)
    # volunteer — только свои и только если > 24h
    can_cancel_any = viewer.role in {ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS}
    is_own_profile = viewer.id == target.id

    return templates.TemplateResponse("public_profile.html", {
        "request": request,
        "user": viewer,
        "target": target,
        "can_edit": viewer.role in {ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS},
        "can_cancel_any": can_cancel_any,
        "is_own_profile": is_own_profile,
        "cutoff_date": cancel_cutoff.date(),
        "cutoff_time": cancel_cutoff.time(),
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
    })


@router.post("/profile/@{username}/cancel/{booking_id}")
def cancel_booking_from_profile(
    username: str,
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    viewer = get_current_user(request, db)
    target = db.query(models.User).filter_by(username=username).first()
    if not target:
        return RedirectResponse("/schedule", status_code=302)

    back = f"/profile/@{username}"

    if viewer.role in {ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS}:
        # Привилегированная отмена — без дедлайна
        ok, msg = cancel_booking_by_id(booking_id, db, actor_id=viewer.id)
    elif viewer.id == target.id:
        # Волонтёр отменяет сам себе — с проверкой 24h
        ok, msg = cancel_booking(target.id, booking_id, db, actor_id=viewer.id)
    else:
        return RedirectResponse(f"{back}?error=Нет прав для отмены", status_code=302)

    if ok:
        return RedirectResponse(f"{back}?success=1", status_code=302)
    from urllib.parse import quote
    return RedirectResponse(f"{back}?error={quote(msg)}", status_code=302)


@router.get("/api/my-upcoming-shifts")
def my_upcoming_shifts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    now = datetime.now()
    bookings = (
        db.query(models.Booking)
        .join(models.Slot)
        .filter(models.Booking.user_id == user.id)
        .filter(models.Slot.date >= now.date())
        .order_by(models.Slot.date, models.Slot.time)
        .all()
    )
    result = []
    for b in bookings:
        slot_dt = datetime.combine(b.slot.date, b.slot.time)
        result.append({
            "booking_id": b.id,
            "slot_id": b.slot.id,
            "direction": b.slot.direction.name,
            "date": b.slot.date.isoformat(),
            "time": b.slot.time.strftime("%H:%M"),
            "datetime_iso": slot_dt.isoformat(),
        })
    return result


@router.get("/api/users/{user_id}/upcoming-shifts")
def user_upcoming_shifts(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    target = db.query(models.User).filter_by(id=user_id, is_active=True).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    now = datetime.now()
    bookings = (
        db.query(models.Booking)
        .join(models.Slot)
        .filter(
            models.Booking.user_id == user_id,
            models.Slot.date > now.date(),
        )
        .order_by(models.Slot.date, models.Slot.time)
        .all()
    )

    return [
        {
            "booking_id": b.id,
            "slot_id": b.slot.id,
            "direction": b.slot.direction.name,
            "date": b.slot.date.isoformat(),
            "time": str(b.slot.time),
        }
        for b in bookings
    ]
