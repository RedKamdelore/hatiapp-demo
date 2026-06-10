import pytest


def test_login_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Вход" in response.text or "login" in response.text.lower()


def test_login_invalid_credentials(client):
    response = client.post("/login", data={
        "username": "nonexistent",
        "password": "wrongpass",
    })
    assert response.status_code == 401


def test_login_valid(client, test_user):
    response = client.post("/login", data={
        "username": "testuser",
        "password": "testpass",
    }, follow_redirects=False)
    
    assert response.status_code == 302
    assert "/schedule" in response.headers.get("location", "")


def test_login_admin_redirect(client, admin_user):
    response = client.post("/login", data={
        "username": "adminuser",
        "password": "adminpass",
    }, follow_redirects=False)
    
    assert response.status_code == 302
    assert "/admin" in response.headers.get("location", "")


def test_logout(client, test_user):
    # Логинимся
    client.post("/login", data={
        "username": "testuser",
        "password": "testpass",
    }, follow_redirects=False)
    
    # Выходим
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/" in response.headers.get("location", "")


def test_protected_route_without_auth(client):
    response = client.get("/schedule", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/" in response.headers.get("location", "")
