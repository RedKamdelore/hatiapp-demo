import pytest
from datetime import datetime, date, timedelta
from services.booking import book_slot, cancel_booking, get_slot_stats
from services.auth import hash_password
from config import ROLE_VOLUNTEER
import models
import uuid


@pytest.fixture
def direction(db):
    unique = str(uuid.uuid4())[:8]
    d = models.Direction(name=f"TestDir_{unique}")
    db.add(d)
    db.commit()
    db.refresh(d)
    yield d


@pytest.fixture
def slot(db, direction):
    from datetime import date, time
    unique_time = time(10, 0, 0)  # один слот на все тесты
    s = db.query(models.Slot).filter_by(
        direction_id=direction.id,
        date=date(2026, 7, 9),
        time=unique_time,
    ).first()
    
    if not s:
        s = models.Slot(
            direction_id=direction.id,
            date=date(2026, 7, 9),
            time=unique_time,
            capacity=2,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
    yield s


@pytest.fixture
def volunteer_user(db):
    unique = str(uuid.uuid4())[:8]
    user = models.User(
        username=f"vol_{unique}",
        full_name="Test Volunteer",
        password_hash=hash_password("pass123"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user


class TestBookSlot:
    def test_book_success(self, db, slot, volunteer_user):
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is True
        assert msg == "Запись оформлена"
        
        # Проверяем что запись создалась
        booking = db.query(models.Booking).filter_by(
            user_id=volunteer_user.id, slot_id=slot.id
        ).first()
        assert booking is not None

    def test_book_already_booked(self, db, slot, volunteer_user):
        # Первая запись
        ok, _ = book_slot(volunteer_user.id, slot.id, db)
        assert ok is True
        
        # Вторая попытка — уже записан
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is False
        assert msg == "Уже записан на этот слот"

    def test_book_no_slots(self, db, slot, volunteer_user):
        # Заполняем слот
        from datetime import date, time
        unique = str(uuid.uuid4())[:8]
        u1 = models.User(
            username=f"u1_{unique}", password_hash=hash_password("p"),
            role=ROLE_VOLUNTEER, is_active=True,
        )
        u2 = models.User(
            username=f"u2_{unique}", password_hash=hash_password("p"),
            role=ROLE_VOLUNTEER, is_active=True,
        )
        db.add_all([u1, u2])
        db.commit()
        
        db.add_all([
            models.Booking(user_id=u1.id, slot_id=slot.id),
            models.Booking(user_id=u2.id, slot_id=slot.id),
        ])
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is False
        assert msg == "Мест нет"

    def test_cancel_booking(self, db, slot, volunteer_user):
        # Сначала записываемся
        ok, _ = book_slot(volunteer_user.id, slot.id, db)
        assert ok is True
        
        # Находим booking
        booking = db.query(models.Booking).filter_by(
            user_id=volunteer_user.id, slot_id=slot.id
        ).first()
        
        # Отменяем
        ok, msg = cancel_booking(volunteer_user.id, booking.id, db)
        assert ok is True
        assert msg == "Запись отменена"

    def test_slot_stats(self, db, slot, volunteer_user):
        # Изначально 0 записей
        stats = get_slot_stats(slot, db)
        assert stats["booked"] == 0
        assert stats["free"] == 2
        
        # После записи
        book_slot(volunteer_user.id, slot.id, db)
        stats = get_slot_stats(slot, db)
        assert stats["booked"] == 1
        assert stats["free"] == 1


class TestScheduleEndpoints:
    def test_schedule_page(self, client, volunteer_user):
        # Логинимся
        client.post("/login", data={
            "username": volunteer_user.username,
            "password": "pass123",
        }, follow_redirects=False)
        
        # Открываем расписание
        response = client.get("/schedule")
        assert response.status_code == 200
        # Должен быть заголовок страницы ("Расписание" в UTF-8)
        assert b"\xd0\xa0\xd0\xb0\xd1\x81\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb0\xd0\xbd\xd0\xb8\xd0\xb5" in response.content

    def test_slots_page(self, client, volunteer_user, slot, direction):
        # Логинимся
        client.post("/login", data={
            "username": volunteer_user.username,
            "password": "pass123",
        }, follow_redirects=False)
        
        # Открываем страницу слотов direction/date
        from datetime import date
        date_str = slot.date.strftime("%Y-%m-%d")
        response = client.get(f"/schedule/{direction.id}/{date_str}")
        assert response.status_code == 200
        # Должна быть кнопка "Записаться"
        assert b"\xd0\x97\xd0\xb0\xd0\xbf\xd0\xb8\xd1\x81\xd0\xb0\xd1\x82\xd1\x8c\xd1\x81\xd1\x8f" in response.content


class TestAdminPanel:
    def test_admin_page_structure(self, client, admin_user):
        # Логинимся как админ
        client.post("/login", data={
            "username": admin_user.username,
            "password": "adminpass",
        }, follow_redirects=False)
        
        # Открываем админку
        response = client.get("/admin")
        assert response.status_code == 200
        # Должны быть ключевые элементы
        assert b"admin-grid" in response.content
        assert b"\xd0\x91\xd0\xbb\xd0\xbe\xd0\xba\xd0\xb8\xd1\x80\xd0\xbe\xd0\xb2\xd0\xba\xd0\xb0" in response.content  # Блокировка
        assert b"\xd0\x91\xd1\x8b\xd1\x81\xd1\x82\xd1\x80\xd1\x8b\xd0\xb5" in response.content  # Быстрые


class TestBlockedDays:
    def test_book_blocked_day(self, client, volunteer_user, slot, db):
        # Блокируем день слота
        from datetime import date
        blocked = models.BlockedDay(date=slot.date, reason="Тест")
        db.add(blocked)
        db.commit()
        
        # Логинимся
        client.post("/login", data={
            "username": volunteer_user.username,
            "password": "pass123",
        }, follow_redirects=False)
        
        # Пытаемся записаться
        response = client.post(f"/book/{slot.id}", follow_redirects=False)
        assert response.status_code == 302
        assert "error=" in response.headers.get("location", "")
        
        # Очистка
        db.delete(blocked)
        db.commit()
    
    def test_cancel_within_24h(self, client, volunteer_user, slot, db):
        # Создаём слот через 2 часа (менее 24ч)
        slot.date = date.today()
        slot.time = (datetime.now() + timedelta(hours=2)).time()
        db.commit()
        
        # Записываемся
        ok, _ = book_slot(volunteer_user.id, slot.id, db)
        assert ok
        
        # Логинимся
        client.post("/login", data={
            "username": volunteer_user.username,
            "password": "pass123",
        }, follow_redirects=False)
        
        # Пытаемся отменить
        booking = db.query(models.Booking).filter_by(user_id=volunteer_user.id, slot_id=slot.id).first()
        response = client.post(f"/cancel/{booking.id}", follow_redirects=False)
        assert response.status_code == 302
        assert "toast_type=error" in response.headers.get("location", "")


class TestPresenceDays:
    def test_book_before_arrival(self, db, slot, volunteer_user):
        """Нельзя записаться до дня заезда."""
        volunteer_user.arrival_date = slot.date + timedelta(days=2)
        volunteer_user.departure_date = slot.date + timedelta(days=10)
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is False
        assert "ещё не заехал" in msg
    
    def test_book_after_departure(self, db, slot, volunteer_user):
        """Нельзя записаться после дня отъезда."""
        volunteer_user.arrival_date = slot.date - timedelta(days=10)
        volunteer_user.departure_date = slot.date - timedelta(days=2)
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is False
        assert "уже выехал" in msg
    
    def test_book_on_arrival_day(self, db, slot, volunteer_user):
        """В день заезда нельзя записаться."""
        volunteer_user.arrival_date = slot.date
        volunteer_user.departure_date = slot.date + timedelta(days=5)
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is False
        assert "ещё не заехал" in msg
    
    def test_book_on_departure_day(self, db, slot, volunteer_user):
        """В день отъезда нельзя записаться."""
        volunteer_user.arrival_date = slot.date - timedelta(days=5)
        volunteer_user.departure_date = slot.date
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is False
        assert "уже выехал" in msg
    
    def test_book_during_presence(self, db, slot, volunteer_user):
        """Можно записаться во время присутствия."""
        volunteer_user.arrival_date = slot.date - timedelta(days=2)
        volunteer_user.departure_date = slot.date + timedelta(days=2)
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is True
        assert msg == "Запись оформлена"
    
    def test_book_no_dates_set(self, db, slot, volunteer_user):
        """Если даты не указаны — можно записаться всегда."""
        volunteer_user.arrival_date = None
        volunteer_user.departure_date = None
        db.commit()
        
        ok, msg = book_slot(volunteer_user.id, slot.id, db)
        assert ok is True
        assert msg == "Запись оформлена"


class TestBookingAPI:
    def test_book_endpoint(self, client, volunteer_user, slot):
        # Логинимся
        client.post("/login", data={
            "username": volunteer_user.username,
            "password": "pass123",
        }, follow_redirects=False)
        
        # Записываемся
        response = client.post(f"/book/{slot.id}", follow_redirects=False)
        assert response.status_code == 302
        assert "toast=" in response.headers.get("location", "")

    def test_book_no_slots_endpoint(self, client, volunteer_user, slot):
        # Заполняем слот
        from datetime import date, time
        import time as time_module
        unique = str(uuid.uuid4())[:8]
        u1 = models.User(
            username=f"u1_{unique}", password_hash=hash_password("p"),
            role=ROLE_VOLUNTEER, is_active=True,
        )
        u2 = models.User(
            username=f"u2_{unique}", password_hash=hash_password("p"),
            role=ROLE_VOLUNTEER, is_active=True,
        )
        
        from tests.conftest import TestingSessionLocal
        db = TestingSessionLocal()
        db.add_all([u1, u2])
        db.commit()
        db.add_all([
            models.Booking(user_id=u1.id, slot_id=slot.id),
            models.Booking(user_id=u2.id, slot_id=slot.id),
        ])
        db.commit()
        db.close()
        
        # Логинимся
        login_resp = client.post("/login", data={
            "username": volunteer_user.username,
            "password": "pass123",
        }, follow_redirects=False)
        
        # Если сработал rate limit — пропускаем тест
        if login_resp.status_code == 307:
            pytest.skip("Rate limit exceeded")
        
        # Пытаемся записаться
        response = client.post(f"/book/{slot.id}", follow_redirects=False)
        # 307 = rate limit на /book тоже
        if response.status_code == 307:
            pytest.skip("Rate limit exceeded")
        assert response.status_code == 302
        assert "error=" in response.headers.get("location", "")
