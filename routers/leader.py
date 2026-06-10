import re

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database import get_db
from services.auth import require_role
from services.booking import get_slot_stats
from config import ROLE_LEADER, ROLE_ADMIN
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_directions(user, db):
    """Возвращает список направлений, где пользователь — руководитель."""
    if user.role == ROLE_ADMIN:
        return []  # админ видит всё через /logs
    return [
        dl.direction for dl in
        db.query(models.DirectionLeader).filter_by(user_id=user.id).all()
    ]


@router.get("/leader", response_class=HTMLResponse)
def leader_panel(request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    directions = get_directions(user, db)

    if not directions:
        return templates.TemplateResponse("leader.html", {
            "request": request, "user": user,
            "directions": [], "days_by_dir": {},
        })

    today = datetime.today().date()
    days_by_dir = {}
    
    for direction in directions:
        dates = db.query(models.Slot.date)\
            .filter(models.Slot.direction_id == direction.id,
                    models.Slot.date >= today)\
            .distinct().order_by(models.Slot.date).all()
        dates = [d[0] for d in dates]

        days = []
        for d in dates:
            slots = db.query(models.Slot).filter_by(
                direction_id=direction.id, date=d
            ).filter(models.Slot.capacity > 0).all()
            total = sum(s.capacity for s in slots)
            booked = sum(get_slot_stats(s, db)["booked"] for s in slots)
            days.append({"date": d, "total": total, "booked": booked})
        
        days_by_dir[direction.id] = days

    return templates.TemplateResponse("leader.html", {
        "request": request, "user": user,
        "directions": directions,
        "days_by_dir": days_by_dir,
    })


@router.get("/leader/day/{date_str}", response_class=HTMLResponse)
def leader_day(date_str: str, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    directions = get_directions(user, db)
    direction_ids = {d.id for d in directions}
    
    if not direction_ids:
        return RedirectResponse("/leader", status_code=302)

    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Показываем слоты для ВСЕХ направлений руководителя
    slots = db.query(models.Slot).filter(
        models.Slot.direction_id.in_(direction_ids),
        models.Slot.date == target_date
    ).filter(models.Slot.capacity > 0)\
     .order_by(models.Slot.time).all()

    slot_data = []
    for s in slots:
        stats = get_slot_stats(s, db)
        slot_data.append({"slot": s, "stats": stats})

    return templates.TemplateResponse("leader_day.html", {
        "request": request, "user": user,
        "directions": directions,
        "target_date": target_date,
        "slot_data": slot_data,
    })


@router.get("/leader/slot/{slot_id}", response_class=HTMLResponse)
def leader_slot(slot_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    directions = get_directions(user, db)
    direction_ids = {d.id for d in directions}

    slot = db.query(models.Slot).filter_by(id=slot_id).first()
    if not slot or (direction_ids and slot.direction_id not in direction_ids):
        return RedirectResponse("/leader", status_code=302)

    # Список записавшихся с отметками присутствия
    bookings = db.query(models.Booking).filter_by(slot_id=slot_id).all()
    booking_data = []
    for b in bookings:
        att = db.query(models.Attendance).filter_by(booking_id=b.id).first()
        booking_data.append({
            "booking": b,
            "attendance": att,
        })

    msg = request.query_params.get("msg")
    return templates.TemplateResponse("leader_slot.html", {
        "request": request, "user": user,
        "slot": slot,
        "direction": slot.direction,
        "booking_data": booking_data,
        "msg": msg,
    })


@router.post("/leader/attendance/{booking_id}")
def mark_attendance(
    booking_id: int,
    request: Request,
    present: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    booking = db.query(models.Booking).filter_by(id=booking_id).first()
    if not booking:
        return RedirectResponse("/leader", status_code=302)

    is_present = present == "1"
    att = db.query(models.Attendance).filter_by(booking_id=booking_id).first()
    if att:
        att.present = is_present
        att.marked_by = user.id
        att.marked_at = datetime.now(timezone.utc)
    else:
        db.add(models.Attendance(
            booking_id=booking_id,
            present=is_present,
            marked_by=user.id,
        ))
    db.commit()
    return RedirectResponse(f"/leader/slot/{booking.slot_id}?msg=saved", status_code=302)


@router.post("/leader/qr-scan")
async def qr_scan(
    request: Request,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Принимает фото, распознаёт QR через OpenCV и отмечает явку."""
    try:
        user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    except Exception:
        return JSONResponse({"ok": False, "error": "Нет доступа"}, status_code=403)

    try:
        import cv2
        import numpy as np
    except ImportError:
        return JSONResponse({"ok": False, "error": "opencv-python не установлен. Запустите: pip install opencv-python-headless"}, status_code=500)

    data = await image.read()
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"ok": False, "error": "Не удалось прочитать изображение"})

    detector = cv2.QRCodeDetector()
    value, _, _ = detector.detectAndDecode(img)

    if not value:
        # Пробуем с повышением контраста
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        img2 = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        value, _, _ = detector.detectAndDecode(img2)

    if not value:
        return JSONResponse({"ok": False, "error": "QR-код не распознан — сфотографируйте чётче"})

    m = re.match(r'^booking:(\d+):user:(\d+):slot:(\d+)$', value)
    if not m:
        return JSONResponse({"ok": False, "error": "Неверный QR-код"})

    booking_id = int(m.group(1))
    booking = db.query(models.Booking).filter_by(id=booking_id).first()
    if not booking:
        return JSONResponse({"ok": False, "error": "Запись не найдена"})

    directions = get_directions(user, db)
    direction_ids = {d.id for d in directions}
    if direction_ids and booking.slot.direction_id not in direction_ids:
        return JSONResponse({"ok": False, "error": "Это не ваше направление"})

    att = db.query(models.Attendance).filter_by(booking_id=booking_id).first()
    if att:
        att.present = True
        att.marked_by = user.id
        att.marked_at = datetime.now(timezone.utc)
    else:
        db.add(models.Attendance(
            booking_id=booking_id,
            present=True,
            marked_by=user.id,
        ))
    db.commit()

    u = booking.user
    return JSONResponse({
        "ok": True,
        "booking_id": booking_id,
        "user_name": u.full_name or u.username,
        "username": u.username,
    })


@router.post("/leader/attendance/{booking_id}/scan")
async def scan_mark_attendance(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """JSON-эндпоинт для отметки явки через QR-сканер. Возвращает JSON."""
    try:
        user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    except Exception:
        return JSONResponse({"ok": False, "error": "Нет доступа"}, status_code=403)

    booking = db.query(models.Booking).filter_by(id=booking_id).first()
    if not booking:
        return JSONResponse({"ok": False, "error": "Запись не найдена"}, status_code=404)

    # Лидер может отмечать только свои направления
    directions = get_directions(user, db)
    direction_ids = {d.id for d in directions}
    if direction_ids and booking.slot.direction_id not in direction_ids:
        return JSONResponse({"ok": False, "error": "Это не ваше направление"}, status_code=403)

    is_present = True
    att = db.query(models.Attendance).filter_by(booking_id=booking_id).first()
    if att:
        att.present = is_present
        att.marked_by = user.id
        att.marked_at = datetime.now(timezone.utc)
    else:
        db.add(models.Attendance(
            booking_id=booking_id,
            present=is_present,
            marked_by=user.id,
        ))
    db.commit()

    u = booking.user
    return JSONResponse({
        "ok": True,
        "booking_id": booking_id,
        "user_name": u.full_name or u.username,
        "username": u.username,
    })


@router.post("/leader/attendance/reset/{booking_id}")
def reset_attendance(booking_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, ROLE_LEADER, ROLE_ADMIN)
    att = db.query(models.Attendance).filter_by(booking_id=booking_id).first()
    if att:
        db.delete(att)
        db.commit()
    booking = db.query(models.Booking).filter_by(id=booking_id).first()
    return RedirectResponse(f"/leader/slot/{booking.slot_id if booking else ''}", status_code=302)
