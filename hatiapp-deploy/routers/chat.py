from fastapi import APIRouter, Request, Depends, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
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


def get_lotos(db: Session):
    """Возвращает первого активного лотоса (для определения receiver_id)."""
    return db.query(models.User).filter_by(role=ROLE_LOTOS, is_active=True).first()


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


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if user.role == ROLE_LOTOS:
        # Лотос видит ВСЕ диалоги, где участвовал любой лотос
        lotos_ids = get_all_lotos_ids(db)
        sent = db.query(models.ChatMessage.receiver_id).filter(models.ChatMessage.sender_id.in_(lotos_ids)).distinct().all()
        received = db.query(models.ChatMessage.sender_id).filter(models.ChatMessage.receiver_id.in_(lotos_ids)).distinct().all()
        user_ids = list(set([r[0] for r in sent] + [r[0] for r in received]))

        chats = []
        for uid in user_ids:
            u = db.query(models.User).filter_by(id=uid).first()
            if not u:
                continue
            # Последнее сообщение между этим пользователем и ЛЮБЫМ лотосом
            last_msg = db.query(models.ChatMessage).filter(
                or_(
                    and_(models.ChatMessage.sender_id == uid, models.ChatMessage.receiver_id.in_(lotos_ids)),
                    and_(models.ChatMessage.sender_id.in_(lotos_ids), models.ChatMessage.receiver_id == uid),
                )
            ).order_by(models.ChatMessage.created_at.desc()).first()
            chats.append({"user": u, "last_msg": last_msg})

        chats.sort(key=lambda x: x["last_msg"].created_at if x["last_msg"] else datetime.min, reverse=True)

        return templates.TemplateResponse("chat_lotos.html", {
            "request": request,
            "user": user,
            "chats": chats,
        })

    # Обычный пользователь — чат со ВСЕМИ лотосами
    lotos_list = db.query(models.User).filter_by(role=ROLE_LOTOS, is_active=True).all()
    lotos_ids = [l.id for l in lotos_list]

    if not lotos_ids:
        return templates.TemplateResponse("chat.html", {
            "request": request, "user": user, "lotos": None, "messages": [],
            "lotos_list": [],
        })

    # Отмечаем прочитанным у всех лотосов
    for lid in lotos_ids:
        mark_read(user.id, lid, db)

    # Показываем все сообщения между пользователем и ЛЮБЫМ лотосом
    messages = db.query(models.ChatMessage).filter(
        or_(
            and_(models.ChatMessage.sender_id == user.id, models.ChatMessage.receiver_id.in_(lotos_ids)),
            and_(models.ChatMessage.sender_id.in_(lotos_ids), models.ChatMessage.receiver_id == user.id),
        )
    ).order_by(models.ChatMessage.created_at.asc()).all()

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "user": user,
        "lotos": lotos_list[0] if lotos_list else None,
        "lotos_list": lotos_list,
        "messages": messages,
    })


@router.get("/chat/with/{target_id}", response_class=HTMLResponse)
def chat_with(target_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user.role not in {ROLE_LOTOS, ROLE_ADMIN}:
        return RedirectResponse("/chat", status_code=302)

    target = db.query(models.User).filter_by(id=target_id).first()
    if not target:
        return RedirectResponse("/chat", status_code=302)

    # Отмечаем прочитанным
    mark_read(user.id, target_id, db)

    if user.role == ROLE_LOTOS:
        # Для лотоса показываем ВСЕ сообщения между этим пользователем и ЛЮБЫМ лотосом
        lotos_ids = get_all_lotos_ids(db)
        messages = db.query(models.ChatMessage).filter(
            or_(
                and_(models.ChatMessage.sender_id == target.id, models.ChatMessage.receiver_id.in_(lotos_ids)),
                and_(models.ChatMessage.sender_id.in_(lotos_ids), models.ChatMessage.receiver_id == target.id),
            )
        ).order_by(models.ChatMessage.created_at.asc()).all()
    else:
        # Для админа — обычный диалог 1 на 1
        messages = db.query(models.ChatMessage).filter(
            or_(
                and_(models.ChatMessage.sender_id == user.id,     models.ChatMessage.receiver_id == target.id),
                and_(models.ChatMessage.sender_id == target.id,   models.ChatMessage.receiver_id == user.id),
            )
        ).order_by(models.ChatMessage.created_at.asc()).all()

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "user": user,
        "lotos": target,
        "lotos_list": [],
        "messages": messages,
        "is_lotos_view": True,
    })


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
    if user.role in {ROLE_LOTOS, ROLE_ADMIN}:
        return RedirectResponse(f"/chat/with/{receiver_id}", status_code=302)
    return RedirectResponse("/chat", status_code=302)


@router.post("/chat/delete/{message_id}")
def delete_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    msg = db.query(models.ChatMessage).filter_by(id=message_id).first()
    if msg and (msg.sender_id == user.id or user.role in {ROLE_LOTOS, ROLE_ADMIN}):
        other_id = msg.receiver_id if msg.sender_id == user.id else msg.sender_id
        db.delete(msg)
        db.commit()
    if user.role in {ROLE_LOTOS, ROLE_ADMIN}:
            return RedirectResponse(f"/chat/with/{other_id}", status_code=302)
    return RedirectResponse("/chat", status_code=302)


@router.post("/chat/read/{other_id}")
def mark_as_read(other_id: int, request: Request, db: Session = Depends(get_db)):
    """Вызывается JS когда пользователь открыт в чате и получает новые сообщения."""
    from fastapi.responses import JSONResponse
    user = get_current_user(request, db)
    mark_read(user.id, other_id, db)
    return JSONResponse({"ok": True})


# ── WebSocket для real-time чата ────────────────────────────────────────────

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    # Создаём свою сессию БД для WebSocket
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

                    # Формируем сообщение для отправки
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

                    # Отправляем получателю через WebSocket
                    await manager.send_to_user(receiver_id, payload)
                    # Отправляем отправителю (для подтверждения)
                    await manager.send_to_user(user_id, payload)

                    # Рассылаем всем лотосам, если участвует лотос
                    receiver = db.query(models.User).filter_by(id=receiver_id).first()
                    lotos_ids = get_all_lotos_ids(db)
                    if receiver and receiver.role == ROLE_LOTOS:
                        # Волонтёр пишет лотосу — всем лотосам
                        for lid in lotos_ids:
                            if lid != receiver_id and lid != user_id:
                                await manager.send_to_user(lid, payload)
                    elif user.role == ROLE_LOTOS:
                        # Лотос пишет волонтёру — всем остальным лотосам
                        for lid in lotos_ids:
                            if lid != user_id:
                                await manager.send_to_user(lid, payload)

                    # Отправляем SSE уведомление
                    if receiver and receiver.role == ROLE_LOTOS:
                        # Волонтёр пишет — всем лотосам
                        for lid in lotos_ids:
                            if lid != user_id:
                                await sse_manager.send_to_user(lid, {
                                    "type": "chat_message",
                                    "sender_id": user_id,
                                    "sender_name": user.full_name or user.username,
                                })
                    else:
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
