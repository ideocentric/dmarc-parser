"""
Tests for docker/seed.py: the seeded super_admin must never get an empty or
default password in production, and existing weak accounts must stop startup.
"""
import importlib.util
from pathlib import Path

import pytest

from core.config import settings
from core.models import Client, User, UserRole
from core.security import hash_password, verify_password
from tests.conftest import TestSession

_spec = importlib.util.spec_from_file_location(
    "seed", Path(__file__).resolve().parent.parent / "docker" / "seed.py"
)
seed_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_module)
seed = seed_module.seed
SeedError = seed_module.SeedError

STRONG = "correct-horse-battery-staple"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reports_base_dir", tmp_path)
    session = TestSession()
    yield session
    session.close()


def _admin(db):
    return db.query(User).filter_by(email="admin@example.com").first()


def _add_super_admin(db, email, password):
    db.add(User(email=email, role=UserRole.super_admin.value,
                password_hash=hash_password(password) if password is not None else None))
    db.commit()


# ── Production: new admin ─────────────────────────────────────────────────────

@pytest.mark.parametrize("env", [
    {},                                   # ADMIN_PASSWORD unset
    {"ADMIN_PASSWORD": ""},               # as .env.prod.example ships it
    {"ADMIN_PASSWORD": "changeme123"},    # the old default
    {"ADMIN_PASSWORD": "short-pw-11"},    # 11 characters
])
def test_production_refuses_missing_weak_or_short_password(db, env):
    with pytest.raises(SeedError):
        seed(db, env=env, app_env="production")
    assert _admin(db) is None


def test_production_creates_admin_that_must_change_password(db):
    log = seed(db, env={"ADMIN_PASSWORD": STRONG}, app_env="production")
    admin = _admin(db)
    assert admin.role == UserRole.super_admin.value
    assert verify_password(STRONG, admin.password_hash)
    assert admin.must_change_password is True
    assert not any(STRONG in line for line in log)


def test_unknown_app_env_is_treated_as_production(db):
    with pytest.raises(SeedError):
        seed(db, env={"ADMIN_PASSWORD": ""}, app_env="staging")


# ── Production: existing accounts ─────────────────────────────────────────────

@pytest.mark.parametrize("weak", ["", "changeme123"])
def test_production_refuses_existing_weak_super_admin(db, weak):
    _add_super_admin(db, "admin@example.com", weak)
    with pytest.raises(SeedError, match="admin@example.com"):
        seed(db, env={"ADMIN_PASSWORD": STRONG}, app_env="production")


def test_production_refuses_any_weak_super_admin_not_just_the_seeded_one(db):
    _add_super_admin(db, "admin@example.com", STRONG)
    _add_super_admin(db, "other@example.com", "")
    with pytest.raises(SeedError, match="other@example.com"):
        seed(db, env={}, app_env="production")


def test_production_accepts_existing_strong_admin_without_admin_password(db):
    _add_super_admin(db, "admin@example.com", STRONG)
    _add_super_admin(db, "sso@example.com", None)   # SSO account, no password
    log = seed(db, env={}, app_env="production")
    assert "  super_admin exists   : admin@example.com" in log


# ── Local environments ────────────────────────────────────────────────────────

@pytest.mark.parametrize("env", [{}, {"ADMIN_PASSWORD": ""}])
def test_local_default_is_documented_password_never_empty(db, env):
    seed(db, env=env, app_env="testing")
    admin = _admin(db)
    assert verify_password("changeme123", admin.password_hash)
    assert not verify_password("", admin.password_hash)
    assert admin.must_change_password is False


def test_local_uses_admin_password_when_set(db):
    seed(db, env={"ADMIN_PASSWORD": "local-pw"}, app_env="development")
    assert verify_password("local-pw", _admin(db).password_hash)


def test_password_never_logged(db):
    log = seed(db, env={}, app_env="development")
    assert not any("changeme123" in line for line in log)


# ── Test client ───────────────────────────────────────────────────────────────

def test_production_creates_no_test_client_unless_named(db):
    seed(db, env={"ADMIN_PASSWORD": STRONG, "TEST_CLIENT_SLUG": ""}, app_env="production")
    assert db.query(Client).count() == 0


def test_production_creates_named_test_client(db):
    seed(db, env={"ADMIN_PASSWORD": STRONG, "TEST_CLIENT_SLUG": "acme"}, app_env="production")
    assert db.query(Client).filter_by(slug="acme").one().name == "Test Client"


def test_local_defaults_to_test_client_and_empty_means_none(db):
    seed(db, env={}, app_env="development")
    assert db.query(Client).filter_by(slug="test-client").count() == 1
    db.query(Client).delete()
    db.commit()
    seed(db, env={"TEST_CLIENT_SLUG": ""}, app_env="development")
    assert db.query(Client).count() == 0
