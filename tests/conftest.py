"""
Shared pytest fixtures for all API tests.
A single in-memory SQLite engine is used so that the get_db override is
consistent regardless of which test files are collected together.
"""
import os

# Must be set before importing the app, which instantiates pydantic Settings.
# These are test-only values — never used outside pytest.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production-use-x1")
# Valid Fernet key: base64url(b"a" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from core.database import get_db
from core.models import Base

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    Base.metadata.create_all(bind=engine)

    # Reset slowapi in-memory rate limit storage before each test so that
    # back-to-back login calls in separate tests don't trip the 5/minute limit.
    from api.limiter import limiter
    if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
        limiter._storage.reset()

    # Disable MFA enforcement so test tokens don't carry msr=True, which would
    # cause the enforce_mfa_setup middleware to block every test API call.
    import api.routes.auth as _auth_routes
    monkeypatch.setattr(_auth_routes, "mfa_required_for_user", lambda *a, **kw: False)

    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def http_client():
    return TestClient(app)