import pytest

from services.auth import hash_password, sign_cookie
from config import COOKIE_NAME, ROLE_ADMIN
import models


@pytest.fixture
def admin_with_session(db, client):
    admin = models.User(
        username="mobile_mass_admin",
        full_name="Mobile Mass Admin",
        password_hash=hash_password("adminpass"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.cookies.set(COOKIE_NAME, sign_cookie(admin.id))
    yield admin
    existing = db.query(models.User).filter_by(id=admin.id).first()
    if existing:
        db.delete(existing)
    db.commit()


def test_admin_page_has_mobile_mass_action_controls(client, admin_with_session):
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.text
    assert 'id="mobile-select-all"' in html
    assert 'mobile-user-checkbox' in html
    assert 'id="mobile-mass-actions"' in html
    assert 'aria-label="Выбрать всех"' in html
