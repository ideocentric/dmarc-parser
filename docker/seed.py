"""
Idempotent seed script — run at every container startup after Alembic migrations.
Creates the initial super_admin and the test client if they don't already exist.

The seeded super_admin's password comes from ADMIN_PASSWORD:
  - Production (any APP_ENV other than "development" or "testing"): it must be
    at least 12 characters and not a known default, and the account has to
    change it on first login. Startup also refuses while any super_admin still
    has an empty or default password, which catches databases seeded before
    this check existed.
  - development / testing: ADMIN_PASSWORD if set, otherwise the documented
    local default "changeme123". Never an empty password.
The password is never written to the log.
"""
import os
import sys

sys.path.insert(0, "/app")

from core.config import settings
from core.database import SessionLocal
from core.models import User, UserRole, Client
from core.security import hash_password, verify_password

LOCAL_ENVS = {"development", "testing"}
LOCAL_DEFAULT_PASSWORD = "changeme123"
MIN_PRODUCTION_PASSWORD_LENGTH = 12
# Passwords never accepted for a production super_admin: blank, and every
# default this script has used.
KNOWN_WEAK_PASSWORDS = ("", LOCAL_DEFAULT_PASSWORD)


class SeedError(Exception):
    """Startup must stop: a super_admin would be, or already is, insecure."""


def is_production(app_env: str) -> bool:
    return app_env not in LOCAL_ENVS


def _admin_password(env, production: bool) -> str:
    password = env.get("ADMIN_PASSWORD", "")
    if not production:
        return password or LOCAL_DEFAULT_PASSWORD
    if len(password) < MIN_PRODUCTION_PASSWORD_LENGTH or password in KNOWN_WEAK_PASSWORDS:
        raise SeedError(
            f"ADMIN_PASSWORD must be set to a password of at least "
            f"{MIN_PRODUCTION_PASSWORD_LENGTH} characters, not a default, before the "
            f"first production start."
        )
    return password


def _refuse_weak_super_admins(db) -> None:
    weak = [
        user.email
        for user in db.query(User).filter_by(role=UserRole.super_admin.value)
        if user.password_hash
        and any(verify_password(p, user.password_hash) for p in KNOWN_WEAK_PASSWORDS)
    ]
    if weak:
        raise SeedError(
            f"super_admin account(s) {', '.join(weak)} have an empty or default password. "
            f"Reset each one without going through this startup script, e.g. "
            f"docker compose -f docker-compose.prod.yml run --rm --entrypoint python api "
            f"-m cli.manage reset-password <email> --temporary"
        )


def seed(db, env=os.environ, app_env: str | None = None) -> list[str]:
    """Seed the database and return log lines. Raises SeedError to stop startup."""
    production = is_production(app_env if app_env is not None else settings.app_env)
    log = []

    admin_email = env.get("ADMIN_EMAIL") or "admin@example.com"
    if production:
        _refuse_weak_super_admins(db)

    if not db.query(User).filter_by(email=admin_email).first():
        password = _admin_password(env, production)
        db.add(User(
            email=admin_email,
            role=UserRole.super_admin.value,
            password_hash=hash_password(password),
            must_change_password=production,
        ))
        db.commit()
        log.append(f"  Created super_admin  : {admin_email}")
    else:
        log.append(f"  super_admin exists   : {admin_email}")

    # Production creates a test client only when one is named explicitly; an
    # empty TEST_CLIENT_SLUG means "none" everywhere.
    client_slug = env.get("TEST_CLIENT_SLUG", "" if production else "test-client")
    client_name = env.get("TEST_CLIENT_NAME") or "Test Client"
    if not client_slug:
        log.append("  Test client          : none (TEST_CLIENT_SLUG empty)")
    elif not db.query(Client).filter_by(slug=client_slug).first():
        db.add(Client(slug=client_slug, name=client_name))
        db.commit()
        settings.client_incoming_dir(client_slug).mkdir(parents=True, exist_ok=True)
        log.append(f"  Created test client  : {client_slug}  ({client_name})")
    else:
        settings.client_incoming_dir(client_slug).mkdir(parents=True, exist_ok=True)
        log.append(f"  Test client exists   : {client_slug}")

    return log


def main() -> int:
    db = SessionLocal()
    try:
        for line in seed(db):
            print(line)
    except SeedError as exc:
        print(f"  SEED REFUSED: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
