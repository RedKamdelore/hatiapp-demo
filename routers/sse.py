import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy import or_, and_, func
from database import SessionLocal
from config import ROLE_LOTOS
from services.sse_manager import sse_manager, sse_stream
import models

router = APIRouter()


def _get_slot_data(slot_id):
    db = SessionLocal()
    try:
        slot = db.query(models.Slot).filter_by(id=slot_id).first()
        if not slot:
            return None
        booked = len(slot.bookings)
        pct = int(booked / slot.capacity * 100) if slot.capacity else 0
        return {
            "booked": booked,
            "capacity": slot.capacity,
            "free": slot.capacity - booked,
            "percent": pct,
            "volunteers": [
                {
                    "name": b.user.full_name or b.user.username,
                    "avatar": b.user.avatar or "",
                    "initial": (b.user.full_name or b.user.username)[0].upper(),
                    "booking_id": b.id,
                    "user_id": b.user_id,
                    "username": b.user.username,
                }
                for b in slot.bookings
            ]
        }
    finally:
        db.close()


def _get_schedule_data(user_id):
    db = SessionLocal()
    try:
        # Слоты текущего пользователя
        my_bookings = db.query(models.Booking.slot_id)\
            .filter_by(user_id=user_id).all()
        my_slot_ids = {b.slot_id for b in my_bookings}

        directions = db.query(models.Direction).order_by(models.Direction.name).all()
        data = []
        for d in directions:
            slots = db.query(models.Slot).filter_by(direction_id=d.id).all()
            total = sum(s.capacity for s in slots)
            if total == 0:
                continue
            booked_total = 0
            slots_data = []
            for s in slots:
                b_count = db.query(func.count(models.Booking.id))\
                    .filter(models.Booking.slot_id == s.id).scalar()
                booked_total += b_count
                pct = int(b_count / s.capacity * 100) if s.capacity else 0
                slots_data.append({
                    "slot_id": s.id,
                    "booked": b_count,
                    "capacity": s.capacity,
                    "free": s.capacity - b_count,
                    "percent": pct,
                    "is_booked": s.id in my_slot_ids,
                })
            data.append({
                "direction_id": d.id,
                "total": total,
                "booked": booked_total,
                "free": total - booked_total,
                "percent": int(booked_total / total * 100) if total else 0,
                "slots": slots_data,
            })
        return data
    finally:
        db.close()


def _get_chat_data(user_id, other_id):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(id=user_id).first()
        lotos_ids = [u.id for u in db.query(models.User).filter_by(role=ROLE_LOTOS, is_active=True).all()]

        if other_id == 0:
            # Обратная совместимость — сообщения с лотосами
            if not lotos_ids:
                return []
            messages = db.query(models.ChatMessage).filter(
                or_(
                    and_(models.ChatMessage.sender_id == user_id, models.ChatMessage.receiver_id.in_(lotos_ids)),
                    and_(models.ChatMessage.sender_id.in_(lotos_ids), models.ChatMessage.receiver_id == user_id),
                )
            ).order_by(models.ChatMessage.created_at.asc()).all()
        elif user and user.role == ROLE_LOTOS:
            # Лотос видит ВСЕ сообщения между этим пользователем и ЛЮБЫМ лотосом
            messages = db.query(models.ChatMessage).filter(
                or_(
                    and_(models.ChatMessage.sender_id == other_id, models.ChatMessage.receiver_id.in_(lotos_ids)),
                    and_(models.ChatMessage.sender_id.in_(lotos_ids), models.ChatMessage.receiver_id == other_id),
                )
            ).order_by(models.ChatMessage.created_at.asc()).all()
        else:
            # Обычный диалог 1 на 1
            messages = db.query(models.ChatMessage).filter(
                or_(
                    and_(models.ChatMessage.sender_id == user_id, models.ChatMessage.receiver_id == other_id),
                    and_(models.ChatMessage.sender_id == other_id, models.ChatMessage.receiver_id == user_id),
                )
            ).order_by(models.ChatMessage.created_at.asc()).all()

        result = []
        for m in messages:
            # Пропускаем удалённые для пользователя
            deleted_for = json.loads(m.deleted_for) if m.deleted_for else []
            if user_id in deleted_for:
                continue
            
            reply_data = None
            if m.reply_to_id:
                reply_msg = db.query(models.ChatMessage).filter_by(id=m.reply_to_id).first()
                if reply_msg:
                    reply_data = {
                        "text": reply_msg.text,
                        "sender_name": reply_msg.sender.full_name or reply_msg.sender.username,
                    }
            
            result.append({
                "id": m.id,
                "text": m.text,
                "sender_id": m.sender_id,
                "sender_name": m.sender.full_name or m.sender.username,
                "sender_username": m.sender.username,
                "sender_role": m.sender.role,
                "sender_avatar": m.sender.avatar or "",
                "sender_initial": (m.sender.full_name or m.sender.username)[0].upper(),
                "time": m.created_at.strftime("%H:%M"),
                "is_me": m.sender_id == user_id,
                "attachment_url": m.attachment_url,
                "reply_to_id": m.reply_to_id,
            "reply_text": reply_data["text"] if reply_data else None,
            "reply_sender_name": reply_data["sender_name"] if reply_data else None,
            "deleted_for": deleted_for,
            "payload": m.payload,
        })
        return result
    finally:
        db.close()


def _get_lotos_ids():
    db = SessionLocal()
    try:
        return [
            u.id for u in 
            db.query(models.User).filter_by(role=ROLE_LOTOS, is_active=True).all()
        ]
    finally:
        db.close()


def _get_notify_data(user_id):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(id=user_id).first()
        lotos_ids = [u.id for u in db.query(models.User).filter_by(role=ROLE_LOTOS, is_active=True).all()]
        
        if user and user.role == ROLE_LOTOS:
            # Для лотоса — по каждому диалогу (ВСЕ сообщения между пользователем и ЛЮБЫМ лотосом)
            sent = db.query(models.ChatMessage.receiver_id).filter(models.ChatMessage.sender_id.in_(lotos_ids)).distinct().all()
            received = db.query(models.ChatMessage.sender_id).filter(models.ChatMessage.receiver_id.in_(lotos_ids)).distinct().all()
            all_ids = list(set([r[0] for r in sent] + [r[0] for r in received]))

            chats = []
            for uid in all_ids:
                if uid in lotos_ids:
                    continue
                    
                read_record = db.query(models.ChatRead).filter_by(
                    user_id=user_id, other_id=uid
                ).first()

                q = db.query(func.count(models.ChatMessage.id)).filter(
                    models.ChatMessage.sender_id == uid,
                    models.ChatMessage.receiver_id.in_(lotos_ids),
                )
                if read_record:
                    q = q.filter(models.ChatMessage.created_at > read_record.read_at)
                unread = q.scalar() or 0
                chats.append({"user_id": uid, "unread": unread})

            total = sum(c["unread"] for c in chats)
            return {"unread": total, "chats": chats}

        else:
            # Для любого пользователя — считаем непрочитанные от ВСЕХ отправителей
            # Находим всех, кто писал пользователю
            senders = db.query(models.ChatMessage.sender_id).filter(
                models.ChatMessage.receiver_id == user_id
            ).distinct().all()
            
            chats = []
            total_unread = 0
            for (sender_id,) in senders:
                read_record = db.query(models.ChatRead).filter_by(
                    user_id=user_id, other_id=sender_id
                ).first()

                q = db.query(func.count(models.ChatMessage.id)).filter(
                    models.ChatMessage.sender_id == sender_id,
                    models.ChatMessage.receiver_id == user_id,
                )
                if read_record:
                    q = q.filter(models.ChatMessage.created_at > read_record.read_at)
                unread = q.scalar() or 0
                if unread > 0:
                    chats.append({"user_id": sender_id, "unread": unread})
                    total_unread += unread
            
            return {"unread": total_unread, "chats": chats}
    finally:
        db.close()


async def sse_generator(fetch_fn, interval=3):
    """Универсальный генератор SSE — запускает sync функцию в потоке."""
    last_key = None
    max_lifetime = 300  # закрываем соединение через 5 минут, браузер переподключится сам
    elapsed = 0
    while elapsed < max_lifetime:
        try:
            data = await asyncio.to_thread(fetch_fn)
            if data is None:
                break
            key = json.dumps(data, ensure_ascii=False, default=str)
            if key != last_key:
                last_key = key
                yield f"data: {key}\n\n"
            # Heartbeat каждые 30 сек чтобы браузер не считал соединение мёртвым
            if elapsed % 30 == 0 and elapsed > 0:
                yield ": ping\n\n"
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(interval)
        elapsed += interval


def make_sse(gen):
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def get_uid(request: Request):
    from services.auth import unsign_cookie
    raw = request.cookies.get("session_token")
    return unsign_cookie(raw) if raw else None


@router.get("/api/notify")
async def api_notify(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"unread": 0, "chats": []})
    data = await asyncio.to_thread(lambda: _get_notify_data(uid))
    return JSONResponse(data)


@router.get("/api/schedule-data")
async def api_schedule_data(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse([])
    data = await asyncio.to_thread(lambda: _get_schedule_data(uid))
    return JSONResponse(data)


@router.get("/api/slot-data/{slot_id}")
async def api_slot_data(slot_id: int, request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({})
    data = await asyncio.to_thread(lambda: _get_slot_data(slot_id))
    return JSONResponse(data or {})


@router.get("/api/chat-data")
async def api_chat_data(request: Request, with_user: int = None):
    uid = get_uid(request)
    if not uid:
        return JSONResponse([])
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(id=uid).first()
        if user and user.role == ROLE_LOTOS:
            # Для лотоса нужен конкретный собеседник
            if not with_user:
                return JSONResponse([])
            other_id = with_user
        else:
            # Для волонтёра other_id не важен — покажем всё равно всех лотосов
            # Передаём 0, внутри _get_chat_data определит сама
            other_id = with_user or 0
    finally:
        db.close()
    
    data = await asyncio.to_thread(lambda: _get_chat_data(uid, other_id))
    return JSONResponse(data)


@router.get("/sse/slot/{slot_id}")
async def sse_slot(slot_id: int, request: Request):
    uid = get_uid(request)
    if not uid:
        return make_sse(iter([]))
    return make_sse(sse_generator(lambda: _get_slot_data(slot_id), interval=3))


@router.get("/sse/schedule")
async def sse_schedule(request: Request):
    uid = get_uid(request)
    if not uid:
        return make_sse(iter([]))
    return make_sse(sse_generator(lambda: _get_schedule_data(uid), interval=4))


@router.get("/sse/chat")
async def sse_chat(request: Request, with_user: int = None):
    uid = get_uid(request)
    if not uid:
        return make_sse(iter([]))
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(id=uid).first()
        if user and user.role == ROLE_LOTOS:
            if not with_user:
                return make_sse(iter([]))
            other_id = with_user
        else:
            other_id = with_user or 0
    finally:
        db.close()
    
    return make_sse(sse_generator(lambda: _get_chat_data(uid, other_id), interval=2))


@router.get("/sse/notify")
async def sse_notify(request: Request):
    uid = get_uid(request)
    if not uid:
        return make_sse(iter([]))
    return make_sse(sse_generator(lambda: _get_notify_data(uid), interval=5))


@router.get("/sse/notify-live")
async def sse_notify_live(request: Request):
    """Push-based SSE уведомления (не polling)."""
    uid = get_uid(request)
    if not uid:
        return make_sse(iter([]))
    return await sse_stream(request, uid)
