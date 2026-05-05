"""
Unit tests for core/client_offboard.py — build_export_zip and purge_client.

Tests run against an in-memory SQLite database via the shared conftest fixtures.
Each test gets a fresh schema (autouse setup_db) so fixtures never bleed between tests.
"""
import csv
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from tests.conftest import TestSession
from core.models import (
    AuthResult, Client, Domain, Flag, ImapConfig,
    ProcessedFile, Record, Report, User, UserClient,
    UserRole, ClientRole,
)
from core.security import hash_password
from core.client_offboard import build_export_zip, purge_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_zip(zip_bytes: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(zip_bytes))


def _csv_rows(zf: zipfile.ZipFile, filename: str) -> list[dict]:
    """Return CSV rows as list[dict] from a member of an open ZipFile."""
    content = zf.read(filename).decode()
    if not content.strip():
        return []
    return list(csv.DictReader(io.StringIO(content)))


def _json_member(zf: zipfile.ZipFile, filename: str) -> dict:
    return json.loads(zf.read(filename).decode())


def _find_member(zf: zipfile.ZipFile, suffix: str) -> str:
    """Return the full ZIP path for the member ending with suffix."""
    matches = [n for n in zf.namelist() if n.endswith(suffix)]
    assert matches, f"No ZIP member ending with {suffix!r}. Members: {zf.namelist()}"
    return matches[0]


def _seed_client_data(db, client) -> dict:
    """
    Insert deterministic data into a client:
      2 reports × 3 records × 2 auth_results + 1 flag per record + 3 processed_files
      + 1 domain + 1 imap_config.
    Returns a dict of expected row counts.
    """
    domain = Domain(client_id=client.id, domain=f"{client.slug}.example.com")
    db.add(domain)
    db.flush()

    for r_idx in range(2):
        report = Report(
            client_id=client.id,
            domain_id=domain.id,
            domain=f"{client.slug}.example.com",
            org_name=f"Reporter-{r_idx}",
            report_id=f"{client.slug}-rpt-{r_idx}",
            begin_date=datetime(2024, 1, r_idx + 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, r_idx + 2, tzinfo=timezone.utc),
            source_filename=f"{client.slug}_report_{r_idx}.xml.gz",
        )
        db.add(report)
        db.flush()

        for rec_idx in range(3):
            record = Record(
                report_id=report.id,
                client_id=client.id,
                source_ip=f"10.{r_idx}.{rec_idx}.1",
                count=10 + rec_idx,
                disposition="none",
                dkim_result="pass",
                spf_result="pass",
            )
            db.add(record)
            db.flush()

            for ar_idx in range(2):
                db.add(AuthResult(
                    record_id=record.id,
                    auth_type="dkim" if ar_idx == 0 else "spf",
                    domain=f"{client.slug}.example.com",
                    result="pass",
                ))

            db.add(Flag(
                record_id=record.id,
                client_id=client.id,
                flag_type="new_sender_ip",
                severity="low",
                detail={"ip": f"10.{r_idx}.{rec_idx}.1", "client": client.slug},
            ))

    for pf_idx in range(3):
        db.add(ProcessedFile(
            client_id=client.id,
            filename=f"{client.slug}_processed_{pf_idx}.xml.gz",
            checksum=f"sha256-{client.slug}-{pf_idx}",
        ))

    db.add(ImapConfig(
        client_id=client.id,
        host="imap.example.com",
        port=993,
        username=f"dmarc@{client.slug}.com",
        encrypted_password="fake-encrypted-password",
        use_ssl=True,
        inbox_folder="INBOX",
        processed_folder="DMARC-Processed",
        poll_interval_minutes=15,
    ))

    db.commit()
    return {
        "reports": 2,
        "records": 6,
        "auth_results": 12,
        "flags": 6,
        "domains": 1,
        "imap_configs": 1,
        "processed_files": 3,
        "user_assignments": 0,  # set by caller after adding users
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_a():
    db = TestSession()
    c = Client(slug="acme-corp", name="Acme Corporation")
    db.add(c)
    db.commit()
    db.refresh(c)
    db.close()
    return c


@pytest.fixture
def client_b():
    db = TestSession()
    c = Client(slug="control-corp", name="Control Corporation")
    db.add(c)
    db.commit()
    db.refresh(c)
    db.close()
    return c


@pytest.fixture
def super_admin():
    db = TestSession()
    u = User(
        email="super@test.com",
        role=UserRole.super_admin.value,
        password_hash=hash_password("pass"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture
def orphan_viewer(client_a):
    """Viewer whose only assignment is client_a — must be deactivated on purge."""
    db = TestSession()
    u = User(
        email="orphan-viewer@test.com",
        role=UserRole.user.value,
        password_hash=hash_password("pass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.viewer.value))
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture
def orphan_admin(client_a):
    """Admin whose only assignment is client_a — must be deactivated on purge."""
    db = TestSession()
    u = User(
        email="orphan-admin@test.com",
        role=UserRole.user.value,
        password_hash=hash_password("pass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.admin.value))
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture
def multi_user(client_a, client_b):
    """Assigned to both clients — must stay active and keep client_b assignment."""
    db = TestSession()
    u = User(
        email="multi@test.com",
        role=UserRole.user.value,
        password_hash=hash_password("pass"),
    )
    db.add(u)
    db.flush()
    db.add(UserClient(user_id=u.id, client_id=client_a.id, role=ClientRole.admin.value))
    db.add(UserClient(user_id=u.id, client_id=client_b.id, role=ClientRole.viewer.value))
    db.commit()
    db.refresh(u)
    db.close()
    return u


# ---------------------------------------------------------------------------
# TestBuildExportZip
# ---------------------------------------------------------------------------

class TestBuildExportZip:

    def test_zip_is_valid_binary(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            assert isinstance(zip_bytes, bytes)
            assert len(zip_bytes) > 0
            with _open_zip(zip_bytes):
                pass  # must not raise
        finally:
            db.close()

    def test_zip_contains_all_expected_files(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                names = zf.namelist()
            expected_suffixes = [
                "README.txt", "client.json", "domains.csv", "users.csv",
                "imap_config.json", "reports.csv", "records.csv",
                "auth_results.csv", "flags.csv",
            ]
            for suffix in expected_suffixes:
                assert any(n.endswith(suffix) for n in names), \
                    f"Missing {suffix!r} in ZIP. Members: {names}"
        finally:
            db.close()

    def test_client_json_fields(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                data = _json_member(zf, _find_member(zf, "client.json"))
            assert data["slug"] == "acme-corp"
            assert data["name"] == "Acme Corporation"
            assert "is_active" in data
            assert "mfa_required_admins" in data
            assert "mfa_required_viewers" in data
            assert "created_at" in data
        finally:
            db.close()

    def test_domains_csv_row_count(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            counts = _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "domains.csv"))
            assert len(rows) == counts["domains"]
        finally:
            db.close()

    def test_users_csv_row_count(self, client_a, orphan_viewer, orphan_admin):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "users.csv"))
            # orphan_viewer and orphan_admin are both assigned to client_a
            assert len(rows) == 2
        finally:
            db.close()

    def test_users_csv_shows_both_roles(self, client_a, orphan_viewer, orphan_admin):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "users.csv"))
            roles = {r["client_role"] for r in rows}
            assert "viewer" in roles
            assert "admin" in roles
        finally:
            db.close()

    def test_imap_password_redacted(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                data = _json_member(zf, _find_member(zf, "imap_config.json"))
            assert data["password"] == "REDACTED"
            # original value must NOT be present
            assert "fake-encrypted-password" not in json.dumps(data)
        finally:
            db.close()

    def test_imap_oauth_secret_redacted(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            # Add an OAuth2 secret to the existing imap_config
            imap = db.query(ImapConfig).filter_by(client_id=client.id).first()
            imap.oauth2_client_secret = "super-secret-oauth-value"
            db.commit()
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                data = _json_member(zf, _find_member(zf, "imap_config.json"))
            assert data["oauth2_client_secret"] == "REDACTED"
            assert "super-secret-oauth-value" not in json.dumps(data)
        finally:
            db.close()

    def test_reports_csv_row_count(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            counts = _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "reports.csv"))
            assert len(rows) == counts["reports"]
        finally:
            db.close()

    def test_records_csv_row_count(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            counts = _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "records.csv"))
            assert len(rows) == counts["records"]
        finally:
            db.close()

    def test_auth_results_csv_row_count(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            counts = _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "auth_results.csv"))
            assert len(rows) == counts["auth_results"]
        finally:
            db.close()

    def test_flags_csv_row_count(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            counts = _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "flags.csv"))
            assert len(rows) == counts["flags"]
        finally:
            db.close()

    def test_flags_csv_detail_json_serialised(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                rows = _csv_rows(zf, _find_member(zf, "flags.csv"))
            for row in rows:
                detail = json.loads(row["detail_json"])
                assert isinstance(detail, dict)
                assert "ip" in detail
        finally:
            db.close()

    def test_control_client_data_not_included(self, client_a, client_b):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            cb = db.get(Client, client_b.id)
            _seed_client_data(db, ca)
            _seed_client_data(db, cb)
            zip_bytes = build_export_zip(ca, db)
            with _open_zip(zip_bytes) as zf:
                report_rows = _csv_rows(zf, _find_member(zf, "reports.csv"))
                record_rows = _csv_rows(zf, _find_member(zf, "records.csv"))
                flag_rows = _csv_rows(zf, _find_member(zf, "flags.csv"))
            # client_b's unique identifier appears in its data
            all_content = (
                json.dumps(report_rows) + json.dumps(record_rows) + json.dumps(flag_rows)
            )
            assert "control-corp" not in all_content
            assert "acme-corp" in all_content
        finally:
            db.close()

    def test_readme_contains_correct_counts(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            counts = _seed_client_data(db, client)
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                readme = zf.read(_find_member(zf, "README.txt")).decode()
            assert str(counts["reports"]) in readme
            assert str(counts["records"]) in readme
            assert str(counts["flags"]) in readme
            assert "acme-corp" in readme
        finally:
            db.close()

    def test_no_imap_config_produces_zip_without_imap_member(self, client_a):
        db = TestSession()
        try:
            client = db.get(Client, client_a.id)
            # Seed data but add no imap_config
            domain = Domain(client_id=client.id, domain="acme-corp.example.com")
            db.add(domain)
            db.commit()
            zip_bytes = build_export_zip(client, db)
            with _open_zip(zip_bytes) as zf:
                names = zf.namelist()
            # ZIP should still be produced successfully
            assert any(n.endswith("client.json") for n in names)
            # No imap_config.json when there is no config
            assert not any(n.endswith("imap_config.json") for n in names)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TestPurgeClient
# ---------------------------------------------------------------------------

class TestPurgeClient:

    def test_all_client_a_data_deleted(self, client_a, client_b):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            _seed_client_data(db, ca)
            purge_client(ca, db)
            assert db.query(Report).filter_by(client_id=client_a.id).count() == 0
            assert db.query(Record).filter_by(client_id=client_a.id).count() == 0
            assert db.query(Flag).filter_by(client_id=client_a.id).count() == 0
            assert db.query(Domain).filter_by(client_id=client_a.id).count() == 0
            assert db.query(ImapConfig).filter_by(client_id=client_a.id).count() == 0
            assert db.query(ProcessedFile).filter_by(client_id=client_a.id).count() == 0
            assert db.query(UserClient).filter_by(client_id=client_a.id).count() == 0
        finally:
            db.close()

    def test_auth_results_deleted(self, client_a):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            counts = _seed_client_data(db, ca)
            record_ids_before = [r.id for r in db.query(Record).filter_by(client_id=client_a.id).all()]
            assert db.query(AuthResult).filter(
                AuthResult.record_id.in_(record_ids_before)
            ).count() == counts["auth_results"]
            purge_client(ca, db)
            assert db.query(AuthResult).filter(
                AuthResult.record_id.in_(record_ids_before)
            ).count() == 0
        finally:
            db.close()

    def test_client_a_row_deleted(self, client_a):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            assert db.query(Client).filter_by(slug="acme-corp").first() is None
        finally:
            db.close()

    def test_control_client_b_data_untouched(self, client_a, client_b):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            cb = db.get(Client, client_b.id)
            _seed_client_data(db, ca)
            cb_counts = _seed_client_data(db, cb)
            purge_client(ca, db)
            assert db.query(Report).filter_by(client_id=client_b.id).count() == cb_counts["reports"]
            assert db.query(Record).filter_by(client_id=client_b.id).count() == cb_counts["records"]
            assert db.query(Flag).filter_by(client_id=client_b.id).count() == cb_counts["flags"]
            assert db.query(Domain).filter_by(client_id=client_b.id).count() == cb_counts["domains"]
            assert db.get(Client, client_b.id) is not None
        finally:
            db.close()

    def test_orphan_viewer_deactivated(self, client_a, orphan_viewer):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            db.expire_all()
            u = db.get(User, orphan_viewer.id)
            assert u.is_active is False
        finally:
            db.close()

    def test_orphan_admin_deactivated(self, client_a, orphan_admin):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            db.expire_all()
            u = db.get(User, orphan_admin.id)
            assert u.is_active is False
        finally:
            db.close()

    def test_multi_user_stays_active(self, client_a, client_b, multi_user):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            db.expire_all()
            u = db.get(User, multi_user.id)
            assert u.is_active is True
        finally:
            db.close()

    def test_multi_user_loses_client_a_assignment(self, client_a, client_b, multi_user):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            remaining = db.query(UserClient).filter_by(
                user_id=multi_user.id, client_id=client_a.id
            ).first()
            assert remaining is None
        finally:
            db.close()

    def test_multi_user_keeps_client_b_assignment(self, client_a, client_b, multi_user):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            remaining = db.query(UserClient).filter_by(
                user_id=multi_user.id, client_id=client_b.id
            ).first()
            assert remaining is not None
            assert remaining.role == ClientRole.viewer.value
        finally:
            db.close()

    def test_summary_deleted_counts_match_pre_purge(self, client_a):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            expected = _seed_client_data(db, ca)
            summary = purge_client(ca, db)
            assert summary["deleted"]["reports"] == expected["reports"]
            assert summary["deleted"]["records"] == expected["records"]
            assert summary["deleted"]["auth_results"] == expected["auth_results"]
            assert summary["deleted"]["flags"] == expected["flags"]
            assert summary["deleted"]["domains"] == expected["domains"]
            assert summary["deleted"]["imap_configs"] == expected["imap_configs"]
            assert summary["deleted"]["processed_files"] == expected["processed_files"]
        finally:
            db.close()

    def test_summary_deactivated_users_list(self, client_a, orphan_viewer, orphan_admin):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            summary = purge_client(ca, db)
            deactivated = set(summary["deactivated_users"])
            assert orphan_viewer.email in deactivated
            assert orphan_admin.email in deactivated
        finally:
            db.close()

    def test_summary_multi_user_not_in_deactivated(self, client_a, client_b, multi_user):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            summary = purge_client(ca, db)
            assert multi_user.email not in summary["deactivated_users"]
        finally:
            db.close()

    def test_summary_slug_and_purged_at_present(self, client_a):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            summary = purge_client(ca, db)
            assert summary["slug"] == "acme-corp"
            assert "purged_at" in summary
            assert summary["purged_at"]  # non-empty string
        finally:
            db.close()

    def test_filesystem_dirs_removed(self, client_a, tmp_path, monkeypatch):
        # Create the expected directory structure under tmp_path
        incoming = tmp_path / "incoming" / "acme-corp"
        archive = tmp_path / "archive" / "acme-corp"
        incoming.mkdir(parents=True)
        archive.mkdir(parents=True)
        (incoming / "test.xml.gz").write_bytes(b"data")
        (archive / "archived.xml.gz").write_bytes(b"data")

        class _FakeSettings:
            def client_incoming_dir(self, slug):
                return tmp_path / "incoming" / slug
            def client_archive_dir(self, slug):
                return tmp_path / "archive" / slug

        import core.client_offboard as mod
        monkeypatch.setattr(mod, "_settings", _FakeSettings())

        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            summary = purge_client(ca, db)
        finally:
            db.close()

        assert not incoming.exists()
        assert not archive.exists()
        assert len(summary["filesystem_removed"]) == 2

    def test_filesystem_nonexistent_dirs_does_not_raise(self, client_a, tmp_path, monkeypatch):
        class _FakeSettings:
            def client_incoming_dir(self, slug):
                return tmp_path / "incoming" / slug  # does not exist
            def client_archive_dir(self, slug):
                return tmp_path / "archive" / slug   # does not exist

        import core.client_offboard as mod
        monkeypatch.setattr(mod, "_settings", _FakeSettings())

        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            summary = purge_client(ca, db)  # must not raise
        finally:
            db.close()

        assert summary["filesystem_removed"] == []

    def test_super_admin_not_affected(self, client_a, super_admin):
        db = TestSession()
        try:
            ca = db.get(Client, client_a.id)
            purge_client(ca, db)
            db.expire_all()
            u = db.get(User, super_admin.id)
            assert u.is_active is True
        finally:
            db.close()