"""
Tests for user management, per-client roles, and password reset endpoints.
"""
import pytest

from tests.conftest import TestSession
from core.models import User, UserClient, Client, UserRole, ClientRole
from core.security import hash_password


# ---------------------------------------------------------------------------
# Fixtures — shared test objects
# ---------------------------------------------------------------------------

@pytest.fixture
def client_a():
    db = TestSession()
    c = Client(slug="client-a", name="Client A")
    db.add(c)
    db.commit()
    db.refresh(c)
    db.close()
    return c


@pytest.fixture
def client_b():
    db = TestSession()
    c = Client(slug="client-b", name="Client B")
    db.add(c)
    db.commit()
    db.refresh(c)
    db.close()
    return c


@pytest.fixture
def super_admin():
    db = TestSession()
    u = User(
        email="super@example.com",
        role=UserRole.super_admin.value,
        password_hash=hash_password("superpass"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture
def client_admin(client_a):
    """Global role 'user', admin for client_a."""
    db = TestSession()
    u = User(
        email="cadmin@example.com",
        role=UserRole.user.value,
        password_hash=hash_password("cadminpass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.admin.value))
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture
def viewer(client_a):
    """Global role 'user', viewer for client_a."""
    db = TestSession()
    u = User(
        email="viewer@example.com",
        role=UserRole.user.value,
        password_hash=hash_password("viewerpass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.viewer.value))
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _token(http_client, email, password):
    r = http_client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_super_admin_sees_all_users(self, http_client, super_admin, client_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.get("/users", headers=_auth(tok))
        assert r.status_code == 200
        emails = {u["email"] for u in r.json()}
        assert {"super@example.com", "cadmin@example.com", "viewer@example.com"} == emails

    def test_client_admin_sees_users_in_their_clients(self, http_client, super_admin, client_admin, viewer):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.get("/users", headers=_auth(tok))
        assert r.status_code == 200
        emails = {u["email"] for u in r.json()}
        # Both client_admin and viewer are in client_a
        assert "cadmin@example.com" in emails
        assert "viewer@example.com" in emails
        # super_admin is in no client
        assert "super@example.com" not in emails

    def test_viewer_cannot_list_users(self, http_client, viewer):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.get("/users", headers=_auth(tok))
        assert r.status_code == 403

    def test_unauthenticated_cannot_list_users(self, http_client):
        r = http_client.get("/users")
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_super_admin_can_create_super_admin(self, http_client, super_admin):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.post("/users", headers=_auth(tok), json={
            "email": "new-super@example.com",
            "password": "newpass123",
            "role": "super_admin",
            "client_roles": [],
        })
        assert r.status_code == 201
        assert r.json()["role"] == "super_admin"

    def test_client_admin_cannot_create_super_admin(self, http_client, client_admin):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.post("/users", headers=_auth(tok), json={
            "email": "wannabe@example.com",
            "password": "pass123",
            "role": "super_admin",
            "client_roles": [],
        })
        assert r.status_code == 403

    def test_super_admin_creates_user_with_per_client_role(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.post("/users", headers=_auth(tok), json={
            "email": "new-user@example.com",
            "password": "pass123",
            "role": "user",
            "client_roles": [{"slug": "client-a", "role": "admin"}],
        })
        assert r.status_code == 201
        data = r.json()
        assert data["role"] == "user"
        assert len(data["client_roles"]) == 1
        assert data["client_roles"][0]["slug"] == "client-a"
        assert data["client_roles"][0]["role"] == "admin"

    def test_duplicate_email_returns_409(self, http_client, super_admin):
        tok = _token(http_client, "super@example.com", "superpass")
        payload = {"email": "super@example.com", "password": "x", "role": "user", "client_roles": []}
        r = http_client.post("/users", headers=_auth(tok), json=payload)
        assert r.status_code == 409

    def test_viewer_cannot_create_user(self, http_client, viewer):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.post("/users", headers=_auth(tok), json={
            "email": "new@example.com",
            "password": "x",
            "role": "user",
            "client_roles": [],
        })
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /users/{id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_user_can_get_own_profile(self, http_client, viewer):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.status_code == 200
        assert r.json()["email"] == "viewer@example.com"

    def test_super_admin_can_get_any_user(self, http_client, super_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.status_code == 200

    def test_client_admin_can_get_user_in_shared_client(self, http_client, client_admin, viewer):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.status_code == 200

    def test_viewer_cannot_get_other_user(self, http_client, viewer, client_admin):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.get(f"/users/{client_admin.id}", headers=_auth(tok))
        assert r.status_code == 403

    def test_nonexistent_user_returns_404(self, http_client, super_admin):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.get("/users/99999", headers=_auth(tok))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /users/{id}
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_super_admin_can_change_global_role(self, http_client, super_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.patch(f"/users/{viewer.id}", headers=_auth(tok), json={"role": "super_admin"})
        assert r.status_code == 200
        assert r.json()["role"] == "super_admin"

    def test_non_super_admin_cannot_change_global_role(self, http_client, client_admin, viewer):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.patch(f"/users/{viewer.id}", headers=_auth(tok), json={"role": "super_admin"})
        assert r.status_code == 403

    def test_super_admin_can_update_client_roles(self, http_client, super_admin, viewer, client_b):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.patch(f"/users/{viewer.id}", headers=_auth(tok), json={
            "client_roles": [{"slug": "client-b", "role": "admin"}],
        })
        assert r.status_code == 200
        slugs = [cr["slug"] for cr in r.json()["client_roles"]]
        assert slugs == ["client-b"]

    def test_non_super_admin_cannot_update_client_assignments(self, http_client, client_admin, viewer, client_b):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.patch(f"/users/{viewer.id}", headers=_auth(tok), json={
            "client_roles": [{"slug": "client-b", "role": "admin"}],
        })
        assert r.status_code == 403

    def test_user_read_includes_must_change_password(self, http_client, super_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.status_code == 200
        assert r.json()["must_change_password"] is False


# ---------------------------------------------------------------------------
# POST /users/{id}/reset-password
# ---------------------------------------------------------------------------

class TestResetPassword:
    def test_super_admin_resets_any_password(self, http_client, super_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.post(
            f"/users/{viewer.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "resetpass99", "temporary": False},
        )
        assert r.status_code == 204
        # Verify the new password works
        assert http_client.post(
            "/auth/login", json={"email": "viewer@example.com", "password": "resetpass99"}
        ).status_code == 200

    def test_temporary_reset_sets_must_change_password(self, http_client, super_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        http_client.post(
            f"/users/{viewer.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "temppass99", "temporary": True},
        )
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.json()["must_change_password"] is True

    def test_permanent_reset_does_not_set_flag(self, http_client, super_admin, viewer):
        tok = _token(http_client, "super@example.com", "superpass")
        http_client.post(
            f"/users/{viewer.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "permpass99", "temporary": False},
        )
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.json()["must_change_password"] is False

    def test_client_admin_resets_user_in_their_client(self, http_client, client_admin, viewer):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.post(
            f"/users/{viewer.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "newpass99", "temporary": False},
        )
        assert r.status_code == 204

    def test_client_admin_cannot_reset_user_outside_their_client(
        self, http_client, client_admin, super_admin
    ):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.post(
            f"/users/{super_admin.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "hackpass", "temporary": False},
        )
        assert r.status_code == 403

    def test_viewer_cannot_reset_other_users_password(self, http_client, viewer, client_admin):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.post(
            f"/users/{client_admin.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "hackpass", "temporary": False},
        )
        assert r.status_code == 403

    def test_cannot_reset_own_password_via_reset_endpoint(self, http_client, super_admin):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.post(
            f"/users/{super_admin.id}/reset-password",
            headers=_auth(tok),
            json={"new_password": "newpass99", "temporary": False},
        )
        assert r.status_code == 400

    def test_reset_nonexistent_user_returns_404(self, http_client, super_admin):
        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.post(
            "/users/99999/reset-password",
            headers=_auth(tok),
            json={"new_password": "x", "temporary": False},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /users/{id}/change-password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_user_can_change_own_password(self, http_client, viewer):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.post(
            f"/users/{viewer.id}/change-password",
            headers=_auth(tok),
            json={"old_password": "viewerpass", "new_password": "updated99"},
        )
        assert r.status_code == 204
        assert http_client.post(
            "/auth/login", json={"email": "viewer@example.com", "password": "updated99"}
        ).status_code == 200

    def test_wrong_old_password_returns_401(self, http_client, viewer):
        tok = _token(http_client, "viewer@example.com", "viewerpass")
        r = http_client.post(
            f"/users/{viewer.id}/change-password",
            headers=_auth(tok),
            json={"old_password": "wrongpass", "new_password": "updated99"},
        )
        assert r.status_code == 401

    def test_change_password_clears_must_change_flag(self, http_client, super_admin, viewer):
        # Super admin sets a temporary password
        admin_tok = _token(http_client, "super@example.com", "superpass")
        http_client.post(
            f"/users/{viewer.id}/reset-password",
            headers=_auth(admin_tok),
            json={"new_password": "temppass99", "temporary": True},
        )
        # Viewer changes their password via change-password
        viewer_tok = _token(http_client, "viewer@example.com", "temppass99")
        http_client.post(
            f"/users/{viewer.id}/change-password",
            headers=_auth(viewer_tok),
            json={"old_password": "temppass99", "new_password": "finalpass99"},
        )
        # Flag should now be cleared
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(admin_tok))
        assert r.json()["must_change_password"] is False

    def test_cannot_change_another_users_password(self, http_client, client_admin, viewer):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.post(
            f"/users/{viewer.id}/change-password",
            headers=_auth(tok),
            json={"old_password": "cadminpass", "new_password": "hackpass"},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# UserRead schema fields
# ---------------------------------------------------------------------------

class TestUserReadSchema:
    def test_me_includes_client_roles(self, http_client, client_admin, client_a):
        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.get("/auth/me", headers=_auth(tok))
        assert r.status_code == 200
        data = r.json()
        assert data["must_change_password"] is False
        assert len(data["client_roles"]) == 1
        assert data["client_roles"][0]["slug"] == "client-a"
        assert data["client_roles"][0]["role"] == "admin"
        assert data["client_slugs"] == ["client-a"]


# ---------------------------------------------------------------------------
# Client disclosure prevention
# ---------------------------------------------------------------------------

class TestClientDisclosure:
    def test_admin_cannot_see_client_b_in_user_listing(
        self, http_client, super_admin, client_admin, viewer, client_a, client_b
    ):
        """
        viewer is in client_a (assigned by the viewer fixture).
        We additionally assign viewer to client_b, which client_admin does NOT manage.
        When client_admin lists users, viewer's client_roles must NOT include client_b.
        """
        # Assign viewer to client_b directly via DB
        db = TestSession()
        db.add(UserClient(user_id=viewer.id, client_id=client_b.id, role=ClientRole.viewer.value))
        db.commit()
        db.close()

        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.get("/users", headers=_auth(tok))
        assert r.status_code == 200

        viewer_data = next(u for u in r.json() if u["email"] == "viewer@example.com")
        slugs = [cr["slug"] for cr in viewer_data["client_roles"]]
        assert "client-a" in slugs        # shared client — visible
        assert "client-b" not in slugs    # not the admin's client — hidden

    def test_admin_cannot_see_client_b_in_get_user(
        self, http_client, super_admin, client_admin, viewer, client_a, client_b
    ):
        """Same check via GET /users/{id}."""
        db = TestSession()
        db.add(UserClient(user_id=viewer.id, client_id=client_b.id, role=ClientRole.viewer.value))
        db.commit()
        db.close()

        tok = _token(http_client, "cadmin@example.com", "cadminpass")
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.status_code == 200

        slugs = [cr["slug"] for cr in r.json()["client_roles"]]
        assert "client-a" in slugs
        assert "client-b" not in slugs

    def test_super_admin_sees_all_client_roles(
        self, http_client, super_admin, viewer, client_a, client_b
    ):
        """super_admin always gets the full picture."""
        db = TestSession()
        db.add(UserClient(user_id=viewer.id, client_id=client_b.id, role=ClientRole.viewer.value))
        db.commit()
        db.close()

        tok = _token(http_client, "super@example.com", "superpass")
        r = http_client.get(f"/users/{viewer.id}", headers=_auth(tok))
        assert r.status_code == 200

        slugs = {cr["slug"] for cr in r.json()["client_roles"]}
        assert slugs == {"client-a", "client-b"}