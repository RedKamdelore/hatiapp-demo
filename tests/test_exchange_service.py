import pytest
from datetime import date, time, datetime, timedelta
from services.auth import hash_password
from services import exchange as exchange_service
from config import ROLE_VOLUNTEER
import models
import uuid


@pytest.fixture
def direction(db):
    d = models.Direction(name=f"Dir_{uuid.uuid4().hex[:6]}")
    db.add(d)
    db.commit()
    db.refresh(d)
    yield d


@pytest.fixture
def slot_a(db, direction):
    s = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=2),
        time=time(10, 0),
        capacity=2,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    yield s


@pytest.fixture
def slot_b(db, direction):
    s = models.Slot(
        direction_id=direction.id,
        date=date.today() + timedelta(days=3),
        time=time(14, 0),
        capacity=2,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    yield s


@pytest.fixture
def vol_a(db):
    u = models.User(
        username=f"va_{uuid.uuid4().hex[:6]}",
        full_name="Vol A",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


@pytest.fixture
def vol_b(db):
    u = models.User(
        username=f"vb_{uuid.uuid4().hex[:6]}",
        full_name="Vol B",
        password_hash=hash_password("p"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u


class TestCreateProposal:
    def test_create_exchange_proposal(self, db, vol_a, vol_b, slot_a, slot_b):
        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
        db.add_all([ba, bb])
        db.commit()

        proposal, error = exchange_service.create_proposal(
            vol_a, vol_b.id, ba.id, bb.id, db
        )

        assert proposal is not None
        assert error == ""
        assert proposal.status == "pending"
        assert proposal.sender_id == vol_a.id
        assert proposal.receiver_id == vol_b.id

    def test_create_proposal_rejects_non_volunteer(self, db, vol_a, slot_a, slot_b):
        admin = models.User(
            username=f"admin_{uuid.uuid4().hex[:6]}",
            full_name="Admin",
            password_hash=hash_password("p"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        db.add(ba)
        db.commit()

        proposal, error = exchange_service.create_proposal(
            admin, vol_a.id, ba.id, ba.id, db
        )
        assert proposal is None
        assert "волонтёры" in error.lower()


class TestAcceptProposal:
    def test_accept_swaps_owners(self, db, vol_a, vol_b, slot_a, slot_b):
        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
        db.add_all([ba, bb])
        db.commit()

        proposal, _ = exchange_service.create_proposal(
            vol_a, vol_b.id, ba.id, bb.id, db
        )

        ok, msg = exchange_service.accept_proposal(proposal, vol_b, db)

        assert ok is True
        assert "обмен" in msg.lower()

        db.refresh(ba)
        db.refresh(bb)
        assert ba.user_id == vol_b.id
        assert bb.user_id == vol_a.id
        assert proposal.status == "accepted"

    def test_accept_fails_on_time_conflict(self, db, vol_a, vol_b, slot_a, slot_b):
        other_direction = models.Direction(name=f"Dir2_{uuid.uuid4().hex[:6]}")
        db.add(other_direction)
        db.commit()
        db.refresh(other_direction)

        conflict = models.Slot(
            direction_id=other_direction.id,
            date=slot_b.date,
            time=slot_b.time,
            capacity=2,
        )
        db.add(conflict)
        db.commit()

        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
        bc = models.Booking(user_id=vol_a.id, slot_id=conflict.id)
        db.add_all([ba, bb, bc])
        db.commit()

        proposal, _ = exchange_service.create_proposal(
            vol_a, vol_b.id, ba.id, bb.id, db
        )

        ok, msg = exchange_service.accept_proposal(proposal, vol_b, db)

        assert ok is False
        assert "конфликт" in msg.lower() or "время" in msg.lower()


class TestDeclineProposal:
    def test_decline_sets_status(self, db, vol_a, vol_b, slot_a, slot_b):
        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
        db.add_all([ba, bb])
        db.commit()

        proposal, _ = exchange_service.create_proposal(
            vol_a, vol_b.id, ba.id, bb.id, db
        )

        ok, msg = exchange_service.decline_proposal(proposal, vol_b, db)

        assert ok is True
        assert proposal.status == "declined"


class TestCancelProposal:
    def test_cancel_sets_status(self, db, vol_a, vol_b, slot_a, slot_b):
        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
        db.add_all([ba, bb])
        db.commit()

        proposal, _ = exchange_service.create_proposal(
            vol_a, vol_b.id, ba.id, bb.id, db
        )

        ok, msg = exchange_service.cancel_proposal(proposal, vol_a, db)

        assert ok is True
        assert proposal.status == "cancelled"


class TestExpireProposals:
    def test_expire_pending_proposals(self, db, vol_a, vol_b, slot_a, slot_b):
        ba = models.Booking(user_id=vol_a.id, slot_id=slot_a.id)
        bb = models.Booking(user_id=vol_b.id, slot_id=slot_b.id)
        db.add_all([ba, bb])
        db.commit()

        proposal, _ = exchange_service.create_proposal(
            vol_a, vol_b.id, ba.id, bb.id, db
        )

        proposal.expires_at = datetime.now() - timedelta(minutes=1)
        db.commit()

        count = exchange_service.expire_pending_proposals(db)

        assert count == 1
        db.refresh(proposal)
        assert proposal.status == "expired"
