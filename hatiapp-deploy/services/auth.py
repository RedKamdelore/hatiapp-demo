import hmac
import hashlib
from passlib.context import CryptContext
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from config import COOKIE_NAME, SECRET_KEY
import models

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# ── Пароли ────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Cookie с HMAC-подписью ────────────────────────────────────────────────────
# Формат: "{user_id}.{hmac_sha256}"
# Это защищает от ручной подмены cookie (раньше хранился просто str(user_id)).

def _make_sig(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_cookie(user_id: int) -> str:
    """Возвращает подписанное значение cookie."""
    payload = str(user_id)
    return f"{payload}.{_make_sig(payload)}"


def unsign_cookie(raw: str) -> int | None:
    """Проверяет подпись и возвращает user_id или None при ошибке."""
    if not raw or "." not in raw:
        return None
    payload, sig = raw.rsplit(".", 1)
    if hmac.compare_digest(sig, _make_sig(payload)):
        try:
            return int(payload)
        except ValueError:
            return None
    return None


# ── Аутентификация ─────────────────────────────────────────────────────────────

def get_current_user(request: Request, db: Session) -> models.User:
    """Возвращает текущего пользователя или кидает 401."""
    raw = request.cookies.get(COOKIE_NAME)
    user_id = unsign_cookie(raw) if raw else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = db.query(models.User).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


def require_role(request: Request, db: Session, *roles: str) -> models.User:
    """Проверяет роль. Пример: require_role(request, db, 'admin', 'leader')"""
    user = get_current_user(request, db)
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return user
