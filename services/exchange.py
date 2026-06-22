from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import models
from services.booking import user_is_present
from config import ROLE_VOLUNTEER

EXCHANGE_LIFETIME_HOURS = 3


def _now():
    return datetime.now()


def _is_volunteer(user: models.User) -> bool:
    return user.role == ROLE_VOLUNTEER


def _slot_in_future(slot: models.Slot) -> bool:
    return datetime.combine(slot.date, slot.time) > _now()


def _time_conflict(user_id: int, slot: models.Slot, exclude_booking_ids: list[int], db: Session) -> bool:
    return db.query(models.Booking).join(models.Slot).filter(
        models.Booking.user_id == user_id,
        models.Booking.id.notin_(exclude_booking_ids),
        models.Slot.date == slot.date,
        models.Slot.time == slot.time,
    ).first() is not None


def _log(db: Session, actor_id: int, action: str, slot_id: int, target_id: int = None):
    db.add(models.ActivityLog(
        user_id=actor_id,
        target_id=target_id,
        action=action,
        slot_id=slot_id,
    ))


def create_proposal(
    sender: models.User,
    receiver_id: int,
    sender_booking_id: int,
    receiver_booking_id: int,
    db: Session,
) -> tuple[models.ExchangeProposal | None, str]:
    if not _is_volunteer(sender):
        return None, "Только волонтёры могут обмениваться сменами"

    receiver = db.query(models.User).filter_by(id=receiver_id, is_active=True).first()
    if not receiver or not _is_volunteer(receiver):
        return None, "Собеседник не найден или не является волонтёром"

    sender_booking = db.query(models.Booking).filter_by(
        id=sender_booking_id, user_id=sender.id
    ).first()
    receiver_booking = db.query(models.Booking).filter_by(
        id=receiver_booking_id, user_id=receiver_id
    ).first()

    if not sender_booking or not receiver_booking:
        return None, "Смена не найдена"

    if not _slot_in_future(sender_booking.slot) or not _slot_in_future(receiver_booking.slot):
        return None, "Можно обмениваться только будущими сменами"

    existing = db.query(models.ExchangeProposal).filter(
        models.ExchangeProposal.status == "pending",
        models.ExchangeProposal.sender_id == sender.id,
        models.ExchangeProposal.receiver_id == receiver.id,
    ).first()
    if existing:
        return None, "Уже есть активное предложение этому человеку"

    expires_at = _now() + timedelta(hours=EXCHANGE_LIFETIME_HOURS)
    proposal = models.ExchangeProposal(
        sender_id=sender.id,
        receiver_id=receiver.id,
        sender_booking_id=sender_booking.id,
        receiver_booking_id=receiver_booking.id,
        status="pending",
        expires_at=expires_at,
    )
    db.add(proposal)
    db.flush()

    _log(db, sender.id, "exchange_proposed", sender_booking.slot_id, receiver.id)
    db.commit()
    return proposal, ""


def accept_proposal(
    proposal: models.ExchangeProposal,
    actor: models.User,
    db: Session,
) -> tuple[bool, str]:
    if proposal.receiver_id != actor.id:
        return False, "Нет прав"
    if proposal.status != "pending":
        return False, "Предложение уже закрыто"
    if proposal.expires_at < _now():
        return False, "Предложение истекло"

    db.refresh(proposal.sender_booking)
    db.refresh(proposal.receiver_booking)

    sender_booking = proposal.sender_booking
    receiver_booking = proposal.receiver_booking

    if sender_booking.user_id != proposal.sender_id or receiver_booking.user_id != proposal.receiver_id:
        return False, "Смены уже изменились"

    new_sender_slot = receiver_booking.slot
    new_receiver_slot = sender_booking.slot

    dup_sender = db.query(models.Booking).filter_by(
        user_id=proposal.sender_id, slot_id=new_sender_slot.id
    ).first()
    dup_receiver = db.query(models.Booking).filter_by(
        user_id=proposal.receiver_id, slot_id=new_receiver_slot.id
    ).first()
    if dup_sender or dup_receiver:
        return False, "Один из участников уже записан на целевой слот"

    exclude_ids = [sender_booking.id, receiver_booking.id]
    if _time_conflict(proposal.sender_id, new_sender_slot, exclude_ids, db):
        return False, "У вас есть другая смена в это время"
    if _time_conflict(proposal.receiver_id, new_receiver_slot, exclude_ids, db):
        return False, "У собеседника есть другая смена в это время"

    sender_booking.user_id, receiver_booking.user_id = receiver_booking.user_id, sender_booking.user_id

    proposal.status = "accepted"
    proposal.resolved_at = _now()

    _log(db, actor.id, "exchange_accepted", sender_booking.slot_id, proposal.sender_id)
    db.commit()
    return True, "Обмен завершён"


def decline_proposal(
    proposal: models.ExchangeProposal,
    actor: models.User,
    db: Session,
) -> tuple[bool, str]:
    if proposal.receiver_id != actor.id:
        return False, "Нет прав"
    if proposal.status != "pending":
        return False, "Предложение уже закрыто"

    proposal.status = "declined"
    proposal.resolved_at = _now()
    _log(db, actor.id, "exchange_declined", proposal.sender_booking.slot_id, proposal.sender_id)
    db.commit()
    return True, "Предложение отклонено"


def cancel_proposal(
    proposal: models.ExchangeProposal,
    actor: models.User,
    db: Session,
) -> tuple[bool, str]:
    if proposal.sender_id != actor.id:
        return False, "Нет прав"
    if proposal.status != "pending":
        return False, "Предложение уже закрыто"

    proposal.status = "cancelled"
    proposal.resolved_at = _now()
    _log(db, actor.id, "exchange_cancelled", proposal.sender_booking.slot_id, proposal.receiver_id)
    db.commit()
    return True, "Предложение отменено"


def expire_pending_proposals(db: Session) -> int:
    proposals = db.query(models.ExchangeProposal).filter(
        models.ExchangeProposal.status == "pending",
        models.ExchangeProposal.expires_at < _now(),
    ).all()
    for p in proposals:
        p.status = "expired"
        p.resolved_at = _now()
        _log(db, p.sender_id, "exchange_expired", p.sender_booking.slot_id, p.receiver_id)
    db.commit()
    return len(proposals)
