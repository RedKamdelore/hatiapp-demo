from passlib.context import CryptContext
from database import SessionLocal
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_VOLUNTEER, ROLE_LOTOS
import models

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

USERS = [
    {"username": "ADIMA",   "full_name": "Администратор",  "password": "ADIMA",  "role": ROLE_ADMIN},
    {"username": "leader1", "full_name": "Руководитель 1", "password": "leader123", "role": ROLE_LEADER},
    {"username": "leader2", "full_name": "Руководитель 2", "password": "leader123", "role": ROLE_LEADER},
    {"username": "vol1",    "full_name": "Волонтёр 1",     "password": "vol123",    "role": ROLE_VOLUNTEER},
    {"username": "vol2",    "full_name": "Волонтёр 2",     "password": "vol123",    "role": ROLE_VOLUNTEER},
    {"username": "vol3",    "full_name": "Волонтёр 3",     "password": "vol123",    "role": ROLE_VOLUNTEER},
    {"username": "lotos",   "full_name": "Лотос",           "password": "lotos123",  "role": ROLE_LOTOS},
]


def seed_users():
    db = SessionLocal()
    try:
        for u in USERS:
            exists = db.query(models.User).filter_by(username=u["username"]).first()
            if not exists:
                db.add(models.User(
                    username=u["username"],
                    full_name=u["full_name"],
                    password_hash=pwd_context.hash(u["password"]),
                    role=u["role"],
                    is_active=True,
                ))
        db.commit()
        print("✅ Пользователи созданы")
    finally:
        db.close()
