import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from services.auth import hash_password, sign_cookie
from config import DATABASE_URL, ROLE_ADMIN, ROLE_VOLUNTEER, COOKIE_NAME
import models

# Тестовая БД в памяти
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_user(db):
    user = models.User(
        username="testuser",
        full_name="Test User",
        password_hash=hash_password("testpass"),
        role=ROLE_VOLUNTEER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


@pytest.fixture
def admin_user(db):
    user = models.User(
        username="adminuser",
        full_name="Admin User",
        password_hash=hash_password("adminpass"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


@pytest.fixture
def admin_with_session(db, client):
    username = "admin_session_user"
    existing = db.query(models.User).filter_by(username=username).first()
    if existing:
        db.delete(existing)
        db.commit()
    user = models.User(
        username=username,
        full_name="Admin Session User",
        password_hash=hash_password("adminpass"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    client.cookies.set(COOKIE_NAME, sign_cookie(user.id))
    yield user
    db.delete(user)
    db.commit()
