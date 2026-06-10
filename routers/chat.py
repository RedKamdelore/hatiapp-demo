from fastapi import APIRouter, Request, Depends, Form, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from datetime import datetime, timezone

from database import get_db
from services.auth import get_current_user
from services.websocket import manager, get_user_id_from_cookie
from services.sse_manager import sse_manager
from config import ROLE_ADMIN, ROLE_LOTOS
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_all_lotos_ids(db: Session) -> set:
    """Возвращает ID всех активных лотосов."""
    return {
        u.id for u in
        db.query(models.User).filter_by(role=ROLE_LOTOS, is_active=True).all()
    }


def mark_read(user_id: int, other_id: int, db: Session):
    """Отмечаем что user_id прочитал переписку с other_id."""
    record = db.query(models.ChatRead).filter_by(
        user_id=user_id, other_id=other_id
    ).first()
    now = datetime.now(timezone.utc)
    if record:
        record.read_at = now
    else:
        db.add(models.ChatRead(user_id=user_id, other_id=other_id, read_at=now))
    db.commit()


def _get_dialogs(user_id: int, db: Session):
    """Возвращает все диалоги пользователя, отсортированные по времени."""
    # Все сообщения где участвует пользователь
    messages = db.query(models.ChatMessage).filter(
        or_(
            models.ChatMessage.sender_id == user_id,
            models.ChatMessage.receiver_id == user_id,
        )
    ).order_by(models.ChatMessage.created_at.desc()).all()

    # Группируем по собеседнику
    dialogs = {}
    for m in messages:
        other_id = m.receiver_id if m.sender_id == user_id else m.sender_id
        if other_id not in dialogs:
            dialogs[other_id] = {"last_msg": m, "unread": 0}
        # Сохраняем самое свежее сообщение
        if m.created_at > dialogs[other_id]["last_msg"].created_at:
            dialogs[other_id]["last_msg"] = m

    # Считаем непрочитанные
    for other_id in dialogs:
        read_record = db.query(models.ChatRead).filter_by(
            user_id=user_id, other_id=other_id
        ).first()
        q = db.query(func.count(models.ChatMessage.id)).filter(
            models.ChatMessage.sender_id == other_id,
            models.ChatMessage.receiver_id == user_id,
        )
        if read_record:
            q = q.filter(models.ChatMessage.created_at > read_record.read_at)
        dialogs[other_id]["unread"] = q.scalar() or 0

    # Преобразуем в список
    lotos_ids = get_all_lotos_ids(db)
    result = []
    for other_id, info in dialogs.items():
        u = db.query(models.User).filter_by(id=other_id).first()
        if not u:
            continue
        result.append({
            "user": u,
            "last_msg": info["last_msg"],
            "unread": info["unread"],
            "is_lotos": u.role == ROLE_LOTOS,
        })

    # Сортируем: лотосы первые, затем по времени
    result.sort(key=lambda x: (
        0 if x["is_lotos"] else 1,
        x["last_msg"].created_at if x["last_msg"] else datetime.min
    ), reverse=True)

    return result


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    dialogs = _get_dialogs(user.id, db)

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "user": user,
        "dialogs": dialogs,
        "view": "list",
    })


@router.get("/chat/with/{target_id}", response_class=HTMLResponse)
def chat_with(target_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    target = db.query(models.User).filter_by(id=target_id, is_active=True).first()
    if not target:
        return RedirectResponse("/chat", status_code=302)

    # Отмечаем прочитанным
    mark_read(user.id, target_id, db)

    lotos_ids = get_all_lotos_ids(db)

    if target.role == ROLE_LOTOS:
        # Чат с лотосом — показываем ВСЕ сообщения с любыми лотосами
        messages = db.query(models.ChatMessage).filter(
            or_(
                and_(models.ChatMessage.sender_id == user.id, models.ChatMessage.receiver_id.in_(lotos_ids)),
                and_(models.ChatMessage.sender_id.in_(lotos_ids), models.ChatMessage.receiver_id == user.id),
            )
        ).order_by(models.ChatMessage.created_at.asc()).all()
    else:
        # Обычный диалог 1 на 1
        messages = db.query(models.ChatMessage).filter(
            or_(
                and_(models.ChatMessage.sender_id == user.id, models.ChatMessage.receiver_id == target.id),
                and_(models.ChatMessage.sender_id == target.id, models.ChatMessage.receiver_id == user.id),
            )
        ).order_by(models.ChatMessage.created_at.asc()).all()

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "user": user,
        "target": target,
        "messages": messages,
        "view": "dialog",
    })


@router.get("/api/users/search")
def search_users(
    q: str = Query("", min_length=1),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Поиск пользователей для нового чата. Исключаем себя, лотосов, неактивных."""
    user = get_current_user(request, db)
    lotos_ids = get_all_lotos_ids(db)

    # Ищем по username и full_name
    query = db.query(models.User).filter(
        models.User.is_active == True,
        models.User.id != user.id,
        ~models.User.id.in_(list(lotos_ids)),
        or_(
            models.User.username.ilike(f"%{q}%"),
            models.User.full_name.ilike(f"%{q}%"),
        )
    ).limit(20).all()

    return JSONResponse([
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "role": u.role,
            "avatar": u.avatar,
        }
        for u in query
    ])


@router.post("/chat/send")
def send_message(
    request: Request,
    text: str = Form(...),
    receiver_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    text = text.strip()
    if text:
        db.add(models.ChatMessage(
            sender_id=user.id,
            receiver_id=receiver_id,
            text=text,
        ))
        db.commit()
    return RedirectResponse(f"/chat/with/{receiver_id}", status_code=302)


@router.post("/chat/delete/{message_id}")
def delete_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    msg = db.query(models.ChatMessage).filter_by(id=message_id).first()
    if msg and (msg.sender_id == user.id or user.role == ROLE_ADMIN):
        db.delete(msg)
        db.commit()
    return RedirectResponse("/chat", status_code=302)


@router.post("/chat/read/{other_id}")
def mark_as_read(other_id: int, request: Request, db: Session = Depends(get_db)):
    """Вызывается JS когда пользователь открыт в чате."""
    user = get_current_user(request, db)
    mark_read(user.id, other_id, db)
    return JSONResponse({"ok": True})


# ── WebSocket для real-time чата ────────────────────────────────────────────

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    from database import SessionLocal
    db = SessionLocal()

    try:
        user_id = await get_user_id_from_cookie(websocket)
        if not user_id:
            await websocket.close(code=1008)
            db.close()
            return

        user = db.query(models.User).filter_by(id=user_id, is_active=True).first()
        if not user:
            await websocket.close(code=1008)
            db.close()
            return

        await manager.connect(websocket, user_id)

        try:
            while True:
                data = await websocket.receive_text()
                import json
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue

                action = msg.get("action")
                if action == "send":
                    text = msg.get("text", "").strip()
                    receiver_id = msg.get("receiver_id")
                    if not text or not receiver_id:
                        continue

                    # Сохраняем в БД
                    db_msg = models.ChatMessage(
                        sender_id=user_id,
                        receiver_id=receiver_id,
                        text=text,
                    )
                    db.add(db_msg)
                    db.commit()
                    db.refresh(db_msg)

                    # Получаем данные получателя
                    receiver = db.query(models.User).filter_by(id=receiver_id).first()

                    # Формируем payload
                    payload = {
                        "action": "new_message",
                        "id": db_msg.id,
                        "sender_id": user_id,
                        "sender_name": user.full_name or user.username,
                        "sender_role": user.role,
                        "sender_avatar": user.avatar,
                        "receiver_id": receiver_id,
                        "receiver_name": receiver.full_name or receiver.username if receiver else None,
                        "receiver_role": receiver.role if receiver else None,
                        "text": text,
                        "created_at": db_msg.created_at.isoformat(),
                    }

                    # Отправляем обоим участникам
                    await manager.send_to_user(receiver_id, payload)
                    await manager.send_to_user(user_id, payload)

                    # Если это чат с лотосом — рассылаем всем лотосам
                    lotos_ids = get_all_lotos_ids(db)
                    if receiver_id in lotos_ids:
                        # Волонтёр пишет лотосу — всем лотосам
                        for lid in lotos_ids:
                            if lid != receiver_id and lid != user_id:
                                await manager.send_to_user(lid, payload)
                                await sse_manager.send_to_user(lid, {
                                    "type": "chat_message",
                                    "sender_id": user_id,
                                    "sender_name": user.full_name or user.username,
                                })
                    elif user.role == ROLE_LOTOS:
                        # Лотос пишет волонтёру — всем остальным лотосам
                        for lid in lotos_ids:
                            if lid != user_id:
                                await manager.send_to_user(lid, payload)
                                await sse_manager.send_to_user(lid, {
                                    "type": "chat_message",
                                    "sender_id": user_id,
                                    "sender_name": user.full_name or user.username,
                                })
                    else:
                        # Обычный чат — отправляем SSE получателю
                        await sse_manager.send_to_user(receiver_id, {
                            "type": "chat_message",
                            "sender_id": user_id,
                            "sender_name": user.full_name or user.username,
                        })

                elif action == "typing":
                    receiver_id = msg.get("receiver_id")
                    if receiver_id:
                        await manager.send_to_user(receiver_id, {
                            "action": "typing",
                            "sender_id": user_id,
                        })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            manager.disconnect(user_id)
            db.close()
    except Exception as e:
        print(f"WebSocket setup error: {e}")
        try:
            await websocket.close(code=1011)
        except:
            pass
        db.close()
