import pytest
from fastapi.testclient import TestClient

from tests.conftest import TestSession
from core.models import User, UserRole
from core.security import hash_password


@pytest.fixture
def client(http_client):
    return http_client


@pytest.fixture
def super_admin_user():
    db = TestSession()
    user = User(
        email="admin@example.com",
        role=UserRole.super_admin.value,
        password_hash=hash_password("testpass123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_success(client, super_admin_user):
    r = client.post("/auth/login", json={"email": "admin@example.com", "password": "testpass123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" not in data          # token is in HttpOnly cookie, not body
    assert "refresh_token" in r.cookies


def test_login_wrong_password(client, super_admin_user):
    r = client.post("/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert r.status_code == 401


def test_me_returns_current_user(client, super_admin_user):
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "testpass123"})
    token = login.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@example.com"
    assert data["role"] == "super_admin"
    assert data["must_change_password"] is False
    assert data["client_roles"] == []
    assert data["client_slugs"] == []


def test_me_rejects_no_token(client):
    r = client.get("/auth/me")
    assert r.status_code in (401, 403)


def test_refresh_token(client, super_admin_user):
    # Cookie path is /api/auth (proxy path) so TestClient won't auto-attach it;
    # read from the login response and inject it directly on the client.
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "testpass123"})
    client.cookies.set("refresh_token", login.cookies["refresh_token"])
    r = client.post("/auth/refresh")
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert "refresh_token" in r.cookies     # rotated cookie issued on each refresh


def test_refresh_with_no_cookie_fails(client, super_admin_user):
    r = client.post("/auth/refresh")
    assert r.status_code == 401