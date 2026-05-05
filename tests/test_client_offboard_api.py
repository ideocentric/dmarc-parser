"""
API endpoint tests for client export and purge.

Tests use the shared in-memory SQLite database and TestClient from conftest.
Covers: auth enforcement, correct responses, isolation of control client,
user deactivation visible in the purge response.
"""
import io
import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tests.conftest import TestSession
from core.models import (
    AuthResult, Client, Domain, Flag, ImapConfig,
    ProcessedFile, Record, Report, User, UserClient,
    UserRole, ClientRole,
)
from core.security import hash_password


# ---------------------------------------------------------------------------
# Helpers shared with the unit tests
# ---------------------------------------------------------------------------

def _token(http_client, email, password):
    r = http_client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_minimal(db, client):
    """Seed enough data for the export to produce a non-trivial ZIP."""
    domain = Domain(client_id=client.id, domain=f"{client.slug}.example.com")
    db.add(domain)
    db.flush()
    report = Report(
        client_id=client.id,
        domain_id=domain.id,
        domain=f"{client.slug}.example.com",
        org_name="Test Reporter",
        report_id=f"{client.slug}-api-test-rpt",
        begin_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 3, 2, tzinfo=timezone.utc),
        source_filename="api_test.xml.gz",
    )
    db.add(report)
    db.flush()
    record = Record(
        report_id=report.id,
        client_id=client.id,
        source_ip="192.0.2.1",
        count=5,
        disposition="none",
        dkim_result="pass",
        spf_result="pass",
    )
    db.add(record)
    db.flush()
    db.add(AuthResult(record_id=record.id, auth_type="dkim", domain=f"{client.slug}.example.com", result="pass"))
    db.add(Flag(
        record_id=record.id,
        client_id=client.id,
        flag_type="new_sender_ip",
        severity="low",
        detail={"ip": "192.0.2.1"},
    ))
    db.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def super_admin():
    db = TestSession()
    u = User(
        email="super@api-test.com",
        role=UserRole.super_admin.value,
        password_hash=hash_password("superpass"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return SimpleNamespace(id=uid, email="super@api-test.com")


@pytest.fixture
def client_a(super_admin):
    """Target client for export/purge tests. Seeded with minimal data."""
    db = TestSession()
    c = Client(slug="acme-api", name="Acme API Test")
    db.add(c)
    db.commit()
    db.refresh(c)
    cid, slug = c.id, c.slug
    _seed_minimal(db, c)
    db.close()
    return SimpleNamespace(id=cid, slug=slug)


@pytest.fixture
def client_b(super_admin):
    """Control client — must be unaffected by purge of client_a."""
    db = TestSession()
    c = Client(slug="control-api", name="Control API Test")
    db.add(c)
    db.commit()
    db.refresh(c)
    cid, slug = c.id, c.slug
    _seed_minimal(db, c)
    db.close()
    return SimpleNamespace(id=cid, slug=slug)


@pytest.fixture
def client_admin(client_a):
    """Global role user with admin on client_a only."""
    db = TestSession()
    u = User(
        email="cadmin@api-test.com",
        role=UserRole.user.value,
        password_hash=hash_password("cadminpass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.admin.value))
    db.commit()
    uid = u.id
    db.close()
    return SimpleNamespace(id=uid, email="cadmin@api-test.com")


@pytest.fixture
def viewer(client_a):
    """Global role user with viewer on client_a only."""
    db = TestSession()
    u = User(
        email="viewer@api-test.com",
        role=UserRole.user.value,
        password_hash=hash_password("viewerpass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.viewer.value))
    db.commit()
    uid = u.id
    db.close()
    return SimpleNamespace(id=uid, email="viewer@api-test.com")


@pytest.fixture
def orphan_viewer(client_a):
    """Viewer with only client_a assignment — should be deactivated on purge."""
    db = TestSession()
    u = User(
        email="orphan@api-test.com",
        role=UserRole.user.value,
        password_hash=hash_password("orphanpass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.viewer.value))
    db.commit()
    uid = u.id
    db.close()
    return SimpleNamespace(id=uid, email="orphan@api-test.com")


# ---------------------------------------------------------------------------
# TestExportClientEndpoint  POST /clients/{slug}/export
# ---------------------------------------------------------------------------

class TestExportClientEndpoint:

    def test_super_admin_can_export(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        assert r.status_code == 200

    def test_response_is_zip_content_type(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        assert "zip" in r.headers.get("content-type", "").lower()

    def test_response_has_content_disposition(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        disposition = r.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".zip" in disposition

    def test_response_body_is_valid_zip(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        assert r.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r.content)):
            pass  # must not raise

    def test_zip_contains_readme_and_client_json(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
        assert any(n.endswith("README.txt") for n in names)
        assert any(n.endswith("client.json") for n in names)

    def test_client_admin_cannot_export(self, http_client, client_admin, client_a):
        tok = _token(http_client, "cadmin@api-test.com", "cadminpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        assert r.status_code == 403

    def test_viewer_cannot_export(self, http_client, viewer, client_a):
        tok = _token(http_client, "viewer@api-test.com", "viewerpass")
        r = http_client.post(f"/clients/{client_a.slug}/export", headers=_auth(tok))
        assert r.status_code == 403

    def test_unauthenticated_cannot_export(self, http_client, client_a):
        r = http_client.post(f"/clients/{client_a.slug}/export")
        assert r.status_code in (401, 403)

    def test_export_nonexistent_client_returns_404(self, http_client, super_admin):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.post("/clients/no-such-client/export", headers=_auth(tok))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# TestPurgeClientEndpoint  DELETE /clients/{slug}
# ---------------------------------------------------------------------------

def _delete_client(http_client, slug, confirm_slug, headers=None):
    """DELETE /clients/{slug} with a JSON body.
    Uses request() because TestClient.delete() does not expose body kwargs."""
    return http_client.request(
        "DELETE",
        f"/clients/{slug}",
        headers=headers,
        json={"confirm_slug": confirm_slug},
    )


class TestPurgeClientEndpoint:

    def test_super_admin_can_purge_with_correct_slug(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        assert r.status_code == 200

    def test_purge_response_has_all_summary_fields(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        data = r.json()
        assert data["slug"] == client_a.slug
        assert "purged_at" in data
        assert "deleted" in data
        assert "deactivated_users" in data
        assert "filesystem_removed" in data

    def test_purge_deleted_counts_are_non_negative(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        for key, val in r.json()["deleted"].items():
            assert val >= 0, f"Negative count for {key}: {val}"

    def test_wrong_confirm_slug_returns_422(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = _delete_client(http_client, client_a.slug, "wrong-slug", _auth(tok))
        assert r.status_code == 422

    def test_missing_confirm_slug_returns_422(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = http_client.request("DELETE", f"/clients/{client_a.slug}", headers=_auth(tok), json={})
        assert r.status_code == 422

    def test_client_admin_cannot_purge(self, http_client, client_admin, client_a):
        tok = _token(http_client, "cadmin@api-test.com", "cadminpass")
        r = _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        assert r.status_code == 403

    def test_viewer_cannot_purge(self, http_client, viewer, client_a):
        tok = _token(http_client, "viewer@api-test.com", "viewerpass")
        r = _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        assert r.status_code == 403

    def test_unauthenticated_cannot_purge(self, http_client, client_a):
        r = _delete_client(http_client, client_a.slug, client_a.slug)
        assert r.status_code in (401, 403)

    def test_purge_nonexistent_client_returns_404(self, http_client, super_admin):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = _delete_client(http_client, "no-such-client", "no-such-client", _auth(tok))
        assert r.status_code == 404

    def test_purged_client_absent_from_list(self, http_client, super_admin, client_a):
        tok = _token(http_client, "super@api-test.com", "superpass")
        _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        r = http_client.get("/clients", headers=_auth(tok))
        assert r.status_code == 200
        slugs = [c["slug"] for c in r.json()]
        assert client_a.slug not in slugs

    def test_deactivated_orphan_user_in_response(self, http_client, super_admin, client_a, orphan_viewer):
        tok = _token(http_client, "super@api-test.com", "superpass")
        r = _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        assert orphan_viewer.email in r.json()["deactivated_users"]

    def test_control_client_still_accessible_after_purge(
        self, http_client, super_admin, client_a, client_b
    ):
        tok = _token(http_client, "super@api-test.com", "superpass")
        _delete_client(http_client, client_a.slug, client_a.slug, _auth(tok))
        r = http_client.get(f"/clients/{client_b.slug}", headers=_auth(tok))
        assert r.status_code == 200
        assert r.json()["slug"] == client_b.slug