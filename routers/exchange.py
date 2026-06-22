from fastapi import APIRouter, Request, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import models
from database import get_db
from services.auth import get_current_user
from services import exchange as exchange_service
from services.sse_manager import sse_manager

router = APIRouter(prefix="/api/exchange-proposals", tags=["exchange"])


def _proposal_to_dict(proposal: models.ExchangeProposal) -> dict:
    sb = proposal.sender_booking
    rb = proposal.receiver_booking
    return {
        "id": proposal.id,
        "status": proposal.status,
        "sender_id": proposal.sender_id,
        "receiver_id": proposal.receiver_id,
        "sender_slot": {
            "id": sb.slot.id,
            "direction": sb.slot.direction.name,
            "date": sb.slot.date.isoformat(),
            "time": str(sb.slot.time),
        },
        "receiver_slot": {
            "id": rb.slot.id,
            "direction": rb.slot.direction.name,
            "date": rb.slot.date.isoformat(),
            "time": str(rb.slot.time),
        },
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
    }


@router.post("")
async def create(
    request: Request,
    receiver_id: int = Form(...),
    sender_booking_id: int = Form(...),
    receiver_booking_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    proposal, error = exchange_service.create_proposal(
        user, receiver_id, sender_booking_id, receiver_booking_id, db
    )
    if not proposal:
        raise HTTPException(status_code=400, detail=error)

    proposal_dict = _proposal_to_dict(proposal)
    payload = {
        "type": "exchange_proposal",
        "proposal_id": proposal.id,
        "status": proposal.status,
        "sender_slot": proposal_dict["sender_slot"],
        "receiver_slot": proposal_dict["receiver_slot"],
    }
    msg = models.ChatMessage(
        sender_id=user.id,
        receiver_id=receiver_id,
        text="Предложение обмена сменами",
        payload=payload,
    )
    db.add(msg)
    db.commit()

    await sse_manager.send_to_user(receiver_id, {"type": "chat_message", "from": user.id})

    return proposal_dict


@router.post("/{proposal_id}/accept")
async def accept(proposal_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    proposal = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    ok, msg = exchange_service.accept_proposal(proposal, user, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _update_chat_card(proposal, db)
    await sse_manager.send_to_user(proposal.sender_id, {"type": "exchange_update", "proposal_id": proposal.id, "status": "accepted"})
    return _proposal_to_dict(proposal)


@router.post("/{proposal_id}/decline")
async def decline(proposal_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    proposal = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    ok, msg = exchange_service.decline_proposal(proposal, user, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _update_chat_card(proposal, db)
    await sse_manager.send_to_user(proposal.sender_id, {"type": "exchange_update", "proposal_id": proposal.id, "status": "declined"})
    return _proposal_to_dict(proposal)


@router.post("/{proposal_id}/cancel")
async def cancel(proposal_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    proposal = db.query(models.ExchangeProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    ok, msg = exchange_service.cancel_proposal(proposal, user, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    _update_chat_card(proposal, db)
    await sse_manager.send_to_user(proposal.receiver_id, {"type": "exchange_update", "proposal_id": proposal.id, "status": "cancelled"})
    return _proposal_to_dict(proposal)


def _update_chat_card(proposal: models.ExchangeProposal, db: Session):
    msgs = db.query(models.ChatMessage).filter(models.ChatMessage.payload.isnot(None)).all()
    msg = next((m for m in msgs if m.payload.get("proposal_id") == proposal.id), None)
    if msg and msg.payload:
        msg.payload["status"] = proposal.status
        flag_modified(msg, "payload")
        db.commit()
