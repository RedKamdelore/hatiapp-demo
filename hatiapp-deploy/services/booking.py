from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import models


def user_is_present(user: models.User, target_date: date) -> bool:
    """Проверяет что человек физически в лагере в target_date.
    
    День заезда и день отъезда считаются отсутствием.
    Если даты не указаны — считаем что всегда доступен.
    """
    if not user.arrival_date or not user.departure_date:
        return True
    return user.arrival_date < target_date < user.departure_date


def cancel_deadline_ok(slot) -> bool:
    """Возвращает True если до смены более 24 часов (волонтёр может отменить)."""
    slot_dt = datetime.combine(slot.date, slot.time)
    return slot_dt > datetime.now() + timedelta(hours=24)


def get_slot_stats(slot: models.Slot, db: Session) -> dict:
    booked = db.query(func.count(models.Booking.id))\
        .filter(models.Booking.slot_id == slot.id).scalar()
    free = slot.capacity - booked
    percent = int((booked / slot.capacity) * 100) if slot.capacity else 0
    return {"booked": booked, "free": free, "percent": percent}


def _log(db, actor_id, action, slot_id, target_id=None):
    db.add(models.ActivityLog(
        user_id=actor_id,
        target_id=target_id,
        action=action,
        slot_id=slot_id,
    ))


import time
import random

def book_slot(user_id: int, slot_id: int, db: Session,
              actor_id: int = None) -> tuple[bool, str]:
    """Записывает пользователя на слот с блокировкой от race condition.
    
    Использует SELECT FOR UPDATE для блокировки слота на время проверки и записи.
    При deadlock делает до 3 попыток с случайной задержкой.
    """
    max_retries = 3
    base_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            # Блокируем слот на чтение и запись — другие пользователи ждут
            slot = db.query(models.Slot).filter_by(id=slot_id).with_for_update().first()
            if not slot:
                return False, "Слот не найден"

            already = db.query(models.Booking).filter_by(user_id=user_id, slot_id=slot_id).first()
            if already:
                return False, "Уже записан на этот слот"

            # Проверка заблокированных дней
            blocked = db.query(models.BlockedDay).filter_by(date=slot.date).first()
            if blocked:
                return False, f"Дата {slot.date.strftime('%d.%m')} заблокирована для записи"

            # Проверка что человек в лагере
            user = db.query(models.User).filter_by(id=user_id).first()
            if user and not user_is_present(user, slot.date):
                if slot.date <= user.arrival_date:
                    return False, f"Волонтёр ещё не заехал. Дата заезда: {user.arrival_date.strftime('%d.%m')}. Обратитесь к Лотосу или руководителю."
                else:
                    return False, f"Волонтёр уже выехал. Дата отъезда: {user.departure_date.strftime('%d.%m')}. Обратитесь к Лотосу или руководителю."

            # Конфликт по времени
            time_conflict = db.query(models.Booking).join(models.Slot).filter(
                models.Booking.user_id == user_id,
                models.Slot.date == slot.date,
                models.Slot.time == slot.time,
            ).first()
            if time_conflict:
                return False, f"Уже записан на {time_conflict.slot.direction.name} в это время"

            # Проверяем свободные места — внутри блокировки, атомарно
            stats = get_slot_stats(slot, db)
            if stats["free"] <= 0:
                return False, "Мест нет"

            # Записываем
            db.add(models.Booking(user_id=user_id, slot_id=slot_id))
            action = "admin_booked" if actor_id and actor_id != user_id else "booked"
            _log(db, actor_id or user_id, action, slot_id, 
                 target_id=user_id if actor_id != user_id else None)
            db.commit()
            return True, "Запись оформлена"
            
        except Exception as e:
            db.rollback()
            if attempt < max_retries - 1:
                # Случайная задержка для предотвращения повторных коллизий
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                time.sleep(delay)
                continue
            else:
                # Все попытки исчерпаны
                if "database is locked" in str(e).lower():
                    return False, "Сервер перегружен, попробуйте позже"
                return False, "Ошибка записи, попробуйте снова"
    
    return False, "Не удалось записаться"


def cancel_booking(user_id: int, booking_id: int, db: Session,
                   actor_id: int = None) -> tuple[bool, str]:
    """
    Отмена записи волонтёром.
    Правило: нельзя отменить запись на смену, которая уже сегодня или прошла.
    Записаться в день смены можно, отменить — нет.
    """
    booking = db.query(models.Booking).filter_by(id=booking_id, user_id=user_id).first()
    if not booking:
        return False, "Запись не найдена"

    # Дедлайн: волонтёр может отменить только если до смены > 24 часов
    if not cancel_deadline_ok(booking.slot):
        return False, "Отмена недоступна — до смены менее 24 часов"

    slot_id = booking.slot_id
    action = "admin_cancelled" if actor_id and actor_id != user_id else "cancelled"
    _log(db, actor_id or user_id, action, slot_id,
         target_id=user_id if actor_id != user_id else None)
    db.delete(booking)
    db.commit()
    return True, "Запись отменена"


def cancel_booking_by_id(booking_id: int, db: Session,
                         actor_id: int = None) -> tuple[bool, str]:
    """Отмена по ID записи без проверки user_id и без дедлайна — для админа/лотоса/руководителя."""
    booking = db.query(models.Booking).filter_by(id=booking_id).first()
    if not booking:
        return False, "Запись не найдена"
    slot_id = booking.slot_id
    target_id = booking.user_id
    action = "admin_cancelled" if actor_id and actor_id != target_id else "cancelled"
    _log(db, actor_id or target_id, action, slot_id, target_id=target_id)
    db.delete(booking)
    db.commit()
    return True, "Запись отменена"


def get_user_bookings(user_id: int, db: Session) -> list:
    return db.query(models.Booking).join(models.Slot).join(models.Direction)\
        .filter(models.Booking.user_id == user_id)\
        .order_by(models.Slot.date, models.Slot.time).all()
