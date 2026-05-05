"""
Idempotent seed script — run at every container startup after Alembic migrations.
Creates the default super_admin and test client if they don't already exist.
"""
import os
import sys

sys.path.insert(0, "/app")

from core.database import SessionLocal
from core.models import User, UserRole, Client
from core.security import hash_password
from core.config import settings

db = SessionLocal()
try:
    admin_email    = os.getenv("ADMIN_EMAIL",      "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD",   "changeme123")
    client_slug    = os.getenv("TEST_CLIENT_SLUG", "test-client")
    client_name    = os.getenv("TEST_CLIENT_NAME", "Test Client")

    if not db.query(User).filter_by(email=admin_email).first():
        db.add(User(email=admin_email, role=UserRole.super_admin.value, password_hash=hash_password(admin_password)))
        db.commit()
        print(f"  Created super_admin  : {admin_email}  (password: {admin_password})")
    else:
        print(f"  super_admin exists   : {admin_email}")

    if not db.query(Client).filter_by(slug=client_slug).first():
        db.add(Client(slug=client_slug, name=client_name))
        db.commit()
        incoming = settings.client_incoming_dir(client_slug)
        incoming.mkdir(parents=True, exist_ok=True)
        print(f"  Created test client  : {client_slug}  ({client_name})")
    else:
        settings.client_incoming_dir(client_slug).mkdir(parents=True, exist_ok=True)
        print(f"  Test client exists   : {client_slug}")

finally:
    db.close()