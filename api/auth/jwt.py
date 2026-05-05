import secrets
from datetime import datetime, timedelta, timezone
import jwt
from jwt import PyJWTError  # noqa: F401 — re-exported for callers
from core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30


def _make_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(
    user_id: int,
    email: str,
    role: str,
    client_ids: list[int],
    must_change_password: bool = False,
    mfa_setup_required: bool = False,
) -> str:
    payload: dict = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "client_ids": client_ids,
        "type": "access",
    }
    if must_change_password:
        payload["mcp"] = True  # checked by enforce_password_change middleware
    if mfa_setup_required:
        payload["msr"] = True  # checked by enforce_mfa_setup middleware
    return _make_token(payload, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: int) -> tuple[str, str]:
    """Return (token_string, jti). Store the JTI in the DB for revocation."""
    jti = secrets.token_urlsafe(32)
    token = _make_token(
        {"sub": str(user_id), "type": "refresh", "jti": jti},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return token, jti


def refresh_token_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises PyJWTError on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def verify_access_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise PyJWTError("Not an access token")
    return payload


def verify_refresh_token(token: str) -> tuple[int, str]:
    """Return (user_id, jti). Raises PyJWTError on invalid token."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise PyJWTError("Not a refresh token")
    return int(payload["sub"]), payload["jti"]


MFA_TOKEN_EXPIRE_MINUTES = 5


def create_mfa_token(user_id: int) -> tuple[str, str]:
    """Return (token, jti). The JTI enables single-use enforcement server-side."""
    jti = secrets.token_urlsafe(32)
    token = _make_token(
        {"sub": str(user_id), "type": "mfa", "jti": jti},
        timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES),
    )
    return token, jti


def verify_mfa_token(token: str) -> tuple[int, str]:
    """Return (user_id, jti). Raises PyJWTError if token is invalid or not an MFA token."""
    payload = decode_token(token)
    if payload.get("type") != "mfa":
        raise PyJWTError("Not an MFA token")
    return int(payload["sub"]), payload["jti"]