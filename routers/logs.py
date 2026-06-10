from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import math
from urllib.parse import quote

from database import get_db
from services.auth import get_current_user
from services.booking import book_slot, cancel_booking_by_id, get_slot_stats
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS, ROLE_VOLUNTEER, ROLE_PERMANENT, BOOKINGS_PER_DAY
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ALLOWED_ROLES = (ROLE_ADMIN, ROLE_LOTOS, ROLE_LEADER)


def can_access(user):
    return user.role in ALLOWED_ROLES


def _get_schedule_dates(db):
    today = datetime.today().date()
    dates = db.query(models.Slot.date)\
        .filter(models.Slot.date >= today)\
        .distinct().order_by(models.Slot.date).all()
    return [d[0] for d in dates]


def _get_not_booked(db, target_date):
    """Возвращает волонтёров которые:
    - Активны и имеют роль volunteer
    - Физически присутствуют в лагере в target_date
    - Не записаны на BOOKINGS_PER_DAY смен в этот день
    """
    volunteers = db.query(models.User).filter(
        models.User.role == ROLE_VOLUNTEER,
        models.User.is_active == True,
    ).all()
    result = []
    for v in volunteers:
        # Проверяем что человек в лагере в этот день
        if v.arrival_date and v.departure_date:
            if not (v.arrival_date < target_date < v.departure_date):
                continue  # Не в лагере — пропускаем
        
        count = db.query(models.Booking).join(models.Slot).filter(
            models.Booking.user_id == v.id,
            models.Slot.date == target_date,
        ).count()
        if count < BOOKINGS_PER_DAY:
            result.append({"user": v, "booked": count, "needed": BOOKINGS_PER_DAY - count})
    return result


@router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not can_access(user):
        return RedirectResponse("/", status_code=302)

    dates = _get_schedule_dates(db)

    # Статус по дням
    days = []
    for d in dates:
        # Только волонтёры в лагере (бессменные работают отдельно)
        volunteers = db.query(models.User).filter(
            models.User.role == ROLE_VOLUNTEER,
            models.User.is_active == True,
        ).all()
        present = []
        for v in volunteers:
            if v.arrival_date and v.departure_date:
                if v.arrival_date < d < v.departure_date:
                    present.append(v)
            else:
                present.append(v)
        not_booked = _get_not_booked(db, d)

        # Считаем хватает ли людей перекрыть день
        # Формула: сколько доступно людей × 2 смены / количество слотов
        slots_day = db.query(models.Slot).filter(models.Slot.date == d).all()
        total_capacity = sum(s.capacity for s in slots_day)
        total_booked = db.query(models.Booking).join(models.Slot).filter(
            models.Slot.date == d
        ).count()
        
        available_people = len(present)
        needed_people = math.ceil(total_capacity / BOOKINGS_PER_DAY) if total_capacity > 0 else 0
        shortage_people = max(0, needed_people - available_people)
        coverage_ok = shortage_people == 0
        
        days.append({
            "date": d,
            "total": len(present),
            "not_booked_count": len(not_booked),
            "all_ok": len(not_booked) == 0,
            "total_capacity": total_capacity,
            "total_booked": total_booked,
            "available_people": available_people,
            "needed_people": needed_people,
            "shortage_people": shortage_people,
            "coverage_ok": coverage_ok,
        })

    # История действий (ActivityLog) с пагинацией
    total = db.query(models.ActivityLog).count()
    total_pages = (total + per_page - 1) // per_page
    page = min(page, max(total_pages, 1))
    offset = (page - 1) * per_page

    logs = db.query(models.ActivityLog)\
        .options(joinedload(models.ActivityLog.actor), 
                 joinedload(models.ActivityLog.target), 
                 joinedload(models.ActivityLog.slot))\
        .order_by(models.ActivityLog.created_at.desc())\
        .offset(offset).limit(per_page).all()

    return templates.TemplateResponse("logs.html", {
        "request": request,
        "user": user,
        "days": days,
        "logs": logs,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/logs/day/{date_str}", response_class=HTMLResponse)
def logs_day(date_str: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not can_access(user):
        return RedirectResponse("/", status_code=302)

    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    not_booked = _get_not_booked(db, target_date)

    # Слоты этого дня
    if user.role == ROLE_LEADER and user.led_directions:
        leader_dir = user.led_directions[0].direction
        slots = db.query(models.Slot).filter(
            models.Slot.direction_id == leader_dir.id,
            models.Slot.date == target_date,
            models.Slot.capacity > 0,
        ).order_by(models.Slot.time).all()
    else:
        slots = db.query(models.Slot).filter(
            models.Slot.date == target_date,
            models.Slot.capacity > 0,
        ).order_by(models.Slot.time).all()

    slot_data = []
    for s in slots:
        stats = get_slot_stats(s, db)
        slot_data.append({
            "slot": s,
            "free": stats["free"],
            "booked": stats["booked"],
        })

    # Направления с доступными местами
    dir_free_map = {}
    for item in slot_data:
        d_id = item["slot"].direction_id
        d_name = item["slot"].direction.name
        if d_id not in dir_free_map:
            dir_free_map[d_id] = {"name": d_name, "total_free": 0}
        dir_free_map[d_id]["total_free"] += item["free"]
    
    available_directions = [
        {"id": d_id, "name": info["name"]}
        for d_id, info in dir_free_map.items()
        if info["total_free"] > 0
    ]
    available_directions.sort(key=lambda x: x["name"])

    # Все слоты (для формы — все даты)
    all_dates = _get_schedule_dates(db)

    msg = request.query_params.get("msg")
    status = request.query_params.get("status")

    return templates.TemplateResponse("logs_day.html", {
        "request": request,
        "user": user,
        "target_date": target_date,
        "not_booked": not_booked,
        "slot_data": slot_data,
        "available_directions": available_directions,
        "all_dates": all_dates,
        "msg": msg,
        "status": status,
    })


@router.get("/logs/day/{date_str}/slots")
def get_slots_for_date(date_str: str, request: Request, db: Session = Depends(get_db)):
    """API — возвращает слоты для выбранной даты (для динамического выпадающего списка)."""
    from fastapi.responses import JSONResponse
    user = get_current_user(request, db)
    if not can_access(user):
        return JSONResponse([])
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    slots = db.query(models.Slot).filter(
        models.Slot.date == target_date,
        models.Slot.capacity > 0,
    ).order_by(models.Slot.time).all()
    result = []
    for s in slots:
        stats = get_slot_stats(s, db)
        result.append({
            "id": s.id,
            "label": f"{s.time.strftime('%H:%M')} — {s.direction.name} ({stats['booked']}/{s.capacity})",
            "free": stats["free"],
        })
    return JSONResponse(result)


@router.post("/logs/book")
def admin_book(
    request: Request,
    user_id: int = Form(...),
    slot_id: int = Form(...),
    redirect_date: str = Form(""),
    db: Session = Depends(get_db),
):
    actor = get_current_user(request, db)
    if not can_access(actor):
        return RedirectResponse("/", status_code=302)
    ok, msg = book_slot(user_id, slot_id, db, actor_id=actor.id)
    if redirect_date:
        return RedirectResponse(
            f"/logs/day/{redirect_date}?toast={quote(msg)}&toast_type={'success' if ok else 'error'}",
            status_code=302
        )
    return RedirectResponse(
        f"/logs?toast={quote(msg)}&toast_type={'success' if ok else 'error'}",
        status_code=302
    )


@router.post("/logs/cancel/{booking_id}")
def admin_cancel(
    booking_id: int,
    request: Request,
    redirect_date: str = Form(""),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    actor = get_current_user(request, db)
    if not can_access(actor):
        return RedirectResponse("/", status_code=302)
    cancel_booking_by_id(booking_id, db, actor_id=actor.id)
    toast = "Запись+отменена"
    if redirect_to:
        return RedirectResponse(f"{redirect_to}?toast={toast}", status_code=302)
    if redirect_date:
        return RedirectResponse(f"/logs/day/{redirect_date}?toast={toast}", status_code=302)
    return RedirectResponse(f"/logs?toast={toast}", status_code=302)


@router.post("/logs/user/{user_id}/toggle-check-in")
def toggle_check_in(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Переключить отметку прибытия волонтёра."""
    user = get_current_user(request, db)
    if not can_access(user):
        return RedirectResponse("/", status_code=302)
    
    u = db.query(models.User).filter_by(id=user_id).first()
    if u and u.role == ROLE_VOLUNTEER:
        u.checked_in = not u.checked_in
        db.commit()
    
    return RedirectResponse(request.headers.get("referer", "/logs"), status_code=302)
