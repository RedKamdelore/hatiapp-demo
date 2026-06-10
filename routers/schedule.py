from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import distinct, func
from datetime import datetime, date, timedelta
from urllib.parse import quote

from database import get_db
from services.auth import get_current_user
from services.booking import cancel_booking, book_slot, get_user_bookings
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS, ROLE_PERMANENT, BOOKINGS_PER_DAY
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Роли без лимита смен
NO_LIMIT_ROLES = (ROLE_ADMIN, ROLE_LEADER, ROLE_LOTOS, ROLE_PERMANENT)


def needs_booking(user) -> bool:
    """Нужно ли этому пользователю записываться на смены."""
    return user.role not in NO_LIMIT_ROLES


def get_all_schedule_dates(db: Session) -> list:
    return sorted(set(row[0] for row in db.query(distinct(models.Slot.date)).all()))


def get_booking_counts_batch(db: Session) -> dict:
    """Возвращает {slot_id: booked_count} одним запросом."""
    return dict(
        db.query(models.Booking.slot_id, func.count(models.Booking.id))
        .group_by(models.Booking.slot_id)
        .all()
    )


def get_user_bookings_per_day(user_id: int, db: Session) -> dict:
    bookings = db.query(models.Booking).filter_by(user_id=user_id).all()
    per_day: dict = {}
    for b in bookings:
        d = b.slot.date
        per_day[d] = per_day.get(d, 0) + 1
    return per_day


@router.get("/schedule", response_class=HTMLResponse)
def schedule(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    dates = get_all_schedule_dates(db)
    directions = db.query(models.Direction).options(
        joinedload(models.Direction.leaders).joinedload(models.DirectionLeader.user)
    ).order_by(models.Direction.name).all()

    # Предпочтения: сортируем — сначала любимые направления
    preferred_ids: set = {p.direction_id for p in
                          db.query(models.UserPreference).filter_by(user_id=user.id).all()}
    directions.sort(key=lambda d: (0 if d.id in preferred_ids else 1, d.name))

    # Данные текущего пользователя
    user_booking_slot_ids = {b.slot_id for b in user.bookings}
    show_status = needs_booking(user)
    bookings_per_day = get_user_bookings_per_day(user.id, db) if show_status else {}

    # Все слоты и счётчики брони — одним запросом каждый (не N+1)
    all_slots = db.query(models.Slot).filter(models.Slot.capacity > 0).all()
    slots_by_dir: dict = {}
    for s in all_slots:
        slots_by_dir.setdefault(s.direction_id, []).append(s)

    booking_counts = get_booking_counts_batch(db)

    result = []
    for d in directions:
        slots = slots_by_dir.get(d.id, [])
        if not slots:
            continue

        total_capacity = sum(s.capacity for s in slots)
        total_booked = sum(booking_counts.get(s.id, 0) for s in slots)

        days_stats = []
        for day in dates:
            day_slots = sorted(
                [s for s in slots if s.date == day],
                key=lambda s: s.time
            )
            if not day_slots:
                days_stats.append({"date": day, "slots": [], "has_slots": False})
                continue

            slot_items = []
            for slot in day_slots:
                booked = booking_counts.get(slot.id, 0)
                pct = int(booked / slot.capacity * 100) if slot.capacity else 0
                slot_items.append({
                    "slot": slot,
                    "booked": booked,
                    "capacity": slot.capacity,
                    "percent": pct,
                    "is_booked": slot.id in user_booking_slot_ids,
                })
            days_stats.append({"date": day, "slots": slot_items, "has_slots": True})

        result.append({
            "direction": d,
            "total_capacity": total_capacity,
            "total_booked": total_booked,
            "free": total_capacity - total_booked,
            "is_preferred": d.id in preferred_ids,
            "days": days_stats,
        })

    days_status = []
    if show_status:
        for day in dates:
            count = bookings_per_day.get(day, 0)
            days_status.append({
                "date": day,
                "count": count,
                "done": count >= BOOKINGS_PER_DAY,
            })

    # Заблокированные дни
    blocked_dates = {bd.date for bd in db.query(models.BlockedDay).all()}

    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "user": user,
        "directions": result,
        "dates": dates,
        "days_status": days_status,
        "bookings_per_day": bookings_per_day,
        "required_per_day": BOOKINGS_PER_DAY,
        "show_status": show_status,
        "user_booking_slot_ids": list(user_booking_slot_ids),
        "blocked_dates": blocked_dates,
    })


@router.get("/schedule/{direction_id}/{slot_date}", response_class=HTMLResponse)
def direction_slots(direction_id: int, slot_date: str,
                    request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    direction = db.query(models.Direction).filter_by(id=direction_id).first()
    if not direction:
        return RedirectResponse("/schedule", status_code=302)

    date_obj = datetime.strptime(slot_date, "%Y-%m-%d").date()
    slots = db.query(models.Slot).filter_by(
        direction_id=direction_id, date=date_obj
    ).order_by(models.Slot.time).all()

    show_status = needs_booking(user)
    bookings_per_day = get_user_bookings_per_day(user.id, db) if show_status else {}
    day_count = bookings_per_day.get(date_obj, 0)
    day_full = show_status and day_count >= BOOKINGS_PER_DAY
    user_booking_ids = {b.slot_id: b.id for b in user.bookings}

    booking_counts = get_booking_counts_batch(db)

    slot_data = []
    for slot in slots:
        if slot.capacity == 0:
            continue
        booked = booking_counts.get(slot.id, 0)
        free = slot.capacity - booked
        pct = int(booked / slot.capacity * 100) if slot.capacity else 0
        is_booked = slot.id in user_booking_ids
        slot_data.append({
            "slot": slot,
            "stats": {"booked": booked, "free": free, "percent": pct},
            "is_booked": is_booked,
            "booking_id": user_booking_ids.get(slot.id),
        })

    # Проверка заблокированного дня
    is_blocked = db.query(models.BlockedDay).filter_by(date=date_obj).first() is not None

    return templates.TemplateResponse("slots.html", {
        "request": request,
        "user": user,
        "direction": direction,
        "slot_data": slot_data,
        "slot_date": date_obj,
        "day_count": day_count,
        "day_full": day_full,
        "required_per_day": BOOKINGS_PER_DAY,
        "show_status": show_status,
        "is_blocked": is_blocked,
    })


@router.post("/book/{slot_id}")
def book(slot_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not needs_booking(user):
        return RedirectResponse("/schedule", status_code=302)

    slot = db.query(models.Slot).filter_by(id=slot_id).first()
    if not slot:
        return RedirectResponse("/schedule", status_code=302)

    bookings_per_day = get_user_bookings_per_day(user.id, db)
    day_count = bookings_per_day.get(slot.date, 0)
    if day_count >= BOOKINGS_PER_DAY:
        return RedirectResponse(
            f"/schedule/{slot.direction_id}/{slot.date.isoformat()}?error=limit",
            status_code=302
        )

    ok, msg = book_slot(user.id, slot_id, db)
    if not ok:
        return RedirectResponse(
            f"/schedule/{slot.direction_id}/{slot.date.isoformat()}?error={quote(msg)}",
            status_code=302
        )
    return RedirectResponse("/schedule?toast=Запись+оформлена&toast_type=success", status_code=302)


@router.post("/cancel/{booking_id}")
def cancel(booking_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not needs_booking(user):
        return RedirectResponse("/me", status_code=302)
    ok, msg = cancel_booking(user.id, booking_id, db)
    if not ok:
        return RedirectResponse(f"/me?toast={quote(msg)}&toast_type=error", status_code=302)
    return RedirectResponse("/me?toast=Запись+отменена&toast_type=success", status_code=302)


@router.get("/me", response_class=HTMLResponse)
def my_bookings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    bookings = get_user_bookings(user.id, db)
    show_status = needs_booking(user)
    bookings_per_day = get_user_bookings_per_day(user.id, db) if show_status else {}
    all_dates = get_all_schedule_dates(db)
    today = date.today()

    days_status = []
    all_done = True
    if show_status:
        for day in all_dates:
            count = bookings_per_day.get(day, 0)
            done = count >= BOOKINGS_PER_DAY
            days_status.append({"date": day, "count": count, "done": done})
        all_done = all(d["done"] for d in days_status)

    error = request.query_params.get("error")
    # Дедлайн 24ч: передаём в шаблон для точного сравнения
    cancel_cutoff = datetime.now() + timedelta(hours=24)

    return templates.TemplateResponse("me.html", {
        "request": request,
        "user": user,
        "bookings": bookings,
        "days_status": days_status,
        "required_per_day": BOOKINGS_PER_DAY,
        "show_status": show_status,
        "all_done": all_done,
        "today": today,
        "cutoff_date": cancel_cutoff.date(),
        "cutoff_time": cancel_cutoff.time(),
        "error": error,
    })
