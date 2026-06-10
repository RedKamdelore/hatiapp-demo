from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date as ddate, time as dtime

from database import get_db
from services.auth import require_role
from config import ROLE_ADMIN
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ── Страница редактора ─────────────────────────────────────────────────────────

@router.get("/admin/slots", response_class=HTMLResponse)
def slots_editor(request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, ROLE_ADMIN)

    directions = db.query(models.Direction).order_by(models.Direction.name).all()

    # Все слоты и брони за два запроса
    all_slots = db.query(models.Slot).order_by(models.Slot.date, models.Slot.time).all()
    booking_counts = dict(
        db.query(models.Booking.slot_id, func.count(models.Booking.id))
        .group_by(models.Booking.slot_id).all()
    )

    # Группируем: direction_id → date → [slot_info]
    by_dir: dict = {}
    for s in all_slots:
        booked = booking_counts.get(s.id, 0)
        by_dir.setdefault(s.direction_id, {}) \
              .setdefault(s.date, []) \
              .append({"slot": s, "booked": booked})

    dir_data = []
    for d in directions:
        by_date = by_dir.get(d.id, {})
        all_slot_infos = [si for slist in by_date.values() for si in slist]
        dir_data.append({
            "direction":      d,
            "by_date":        sorted(by_date.items()),   # [(date, [infos]), ...]
            "total_capacity": sum(si["slot"].capacity for si in all_slot_infos),
            "total_booked":   sum(si["booked"]        for si in all_slot_infos),
            "slot_count":     len(all_slot_infos),
        })

    return templates.TemplateResponse("admin_slots.html", {
        "request":    request,
        "user":       user,
        "dir_data":   dir_data,
        "directions": directions,
    })


# ── API: изменить вместимость слота ───────────────────────────────────────────

@router.post("/admin/slots/{slot_id}/capacity")
async def update_capacity(slot_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, ROLE_ADMIN)
    body = await request.json()

    try:
        capacity = int(body.get("capacity", -1))
    except (ValueError, TypeError):
        return JSONResponse({"ok": False, "error": "Неверное значение"}, status_code=400)

    if capacity < 0:
        return JSONResponse({"ok": False, "error": "Вместимость не может быть отрицательной"}, status_code=400)

    slot = db.query(models.Slot).filter_by(id=slot_id).first()
    if not slot:
        return JSONResponse({"ok": False, "error": "Слот не найден"}, status_code=404)

    booked = db.query(func.count(models.Booking.id)).filter_by(slot_id=slot_id).scalar()
    if capacity < booked:
        return JSONResponse(
            {"ok": False, "error": f"Уже записано {booked} — нельзя поставить меньше"},
            status_code=400,
        )

    slot.capacity = capacity
    db.commit()
    return JSONResponse({"ok": True, "capacity": capacity, "booked": booked})


# ── API: удалить слот ─────────────────────────────────────────────────────────

@router.post("/admin/slots/{slot_id}/delete")
async def delete_slot(slot_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, ROLE_ADMIN)

    slot = db.query(models.Slot).filter_by(id=slot_id).first()
    if not slot:
        return JSONResponse({"ok": False, "error": "Слот не найден"}, status_code=404)

    booked = db.query(func.count(models.Booking.id)).filter_by(slot_id=slot_id).scalar()
    if booked > 0:
        return JSONResponse(
            {"ok": False, "error": f"Нельзя удалить — {booked} чел. записано"},
            status_code=400,
        )

    db.delete(slot)
    db.commit()
    return JSONResponse({"ok": True})


# ── API: добавить слот ────────────────────────────────────────────────────────

@router.post("/admin/slots/add")
async def add_slot(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, ROLE_ADMIN)
    body = await request.json()

    try:
        direction_id = int(body["direction_id"])
        slot_date    = ddate.fromisoformat(body["date"])
        h, m         = body["time"].split(":")
        slot_time    = dtime(int(h), int(m))
        capacity     = int(body["capacity"])
    except Exception:
        return JSONResponse({"ok": False, "error": "Неверный формат данных"}, status_code=400)

    if capacity <= 0:
        return JSONResponse({"ok": False, "error": "Вместимость должна быть больше 0"}, status_code=400)

    if not db.query(models.Direction).filter_by(id=direction_id).first():
        return JSONResponse({"ok": False, "error": "Направление не найдено"}, status_code=404)

    if db.query(models.Slot).filter_by(
        direction_id=direction_id, date=slot_date, time=slot_time
    ).first():
        return JSONResponse({"ok": False, "error": "Такой слот уже существует"}, status_code=400)

    slot = models.Slot(
        direction_id=direction_id,
        date=slot_date,
        time=slot_time,
        capacity=capacity,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)

    return JSONResponse({
        "ok": True,
        "slot": {
            "id":       slot.id,
            "date":     slot.date.isoformat(),
            "date_fmt": slot.date.strftime("%d.%m"),
            "time":     slot.time.strftime("%H:%M"),
            "capacity": slot.capacity,
            "booked":   0,
        },
    })


# ── API: добавить направление ─────────────────────────────────────────────────

@router.post("/admin/directions/add")
async def add_direction(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, ROLE_ADMIN)
    body = await request.json()

    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Название не может быть пустым"}, status_code=400)

    if db.query(models.Direction).filter_by(name=name).first():
        return JSONResponse({"ok": False, "error": "Направление с таким названием уже существует"}, status_code=400)

    direction = models.Direction(name=name)
    db.add(direction)
    db.commit()
    db.refresh(direction)

    return JSONResponse({"ok": True, "direction": {"id": direction.id, "name": direction.name}})


# ── API: удалить направление ──────────────────────────────────────────────────

@router.post("/admin/directions/{direction_id}/delete")
async def delete_direction(direction_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, ROLE_ADMIN)

    direction = db.query(models.Direction).filter_by(id=direction_id).first()
    if not direction:
        return JSONResponse({"ok": False, "error": "Направление не найдено"}, status_code=404)

    # Проверяем активные бронирования
    slots = db.query(models.Slot).filter_by(direction_id=direction_id).all()
    slot_ids = [s.id for s in slots]
    slot_count = len(slot_ids)

    if slot_ids:
        booking_count = db.query(func.count(models.Booking.id)).filter(
            models.Booking.slot_id.in_(slot_ids)
        ).scalar() or 0
        if booking_count > 0:
            return JSONResponse({
                "ok": False,
                "error": f"Нельзя удалить — {booking_count} записей. Сначала отмените все записи.",
            }, status_code=400)

    db.delete(direction)
    db.commit()
    return JSONResponse({"ok": True, "slot_count": slot_count})


# ── API: обновить направление (название + описание) ───────────────────────────

@router.post("/admin/directions/{direction_id}/update")
async def update_direction(direction_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, ROLE_ADMIN)
    body = await request.json()

    direction = db.query(models.Direction).filter_by(id=direction_id).first()
    if not direction:
        return JSONResponse({"ok": False, "error": "Направление не найдено"}, status_code=404)

    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()

    if not name:
        return JSONResponse({"ok": False, "error": "Название не может быть пустым"}, status_code=400)

    # Проверяем уникальность (кроме самого себя)
    exists = db.query(models.Direction).filter(
        models.Direction.name == name,
        models.Direction.id != direction_id,
    ).first()
    if exists:
        return JSONResponse({"ok": False, "error": "Направление с таким названием уже существует"}, status_code=400)

    direction.name = name
    direction.description = description or None
    db.commit()

    return JSONResponse({
        "ok": True,
        "direction": {
            "id": direction.id,
            "name": direction.name,
            "description": direction.description,
        },
    })
