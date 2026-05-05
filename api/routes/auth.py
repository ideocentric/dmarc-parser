import base64
import io
import logging
import threading
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jwt import PyJWTError
from sqlalchemy.orm import Session

from api.auth.jwt import (
    create_access_token, create_refresh_token, verify_refresh_token,
    create_mfa_token, verify_mfa_token,
    refresh_token_expires_at, REFRESH_TOKEN_EXPIRE_DAYS, MFA_TOKEN_EXPIRE_MINUTES,
)
from api.limiter import limiter
from api.auth.mfa_policy import mfa_required_for_user
from api.deps import get_current_user, get_db
from core.config import settings
from core.crypto import encrypt, decrypt
from core.models import User, UserRole, RefreshToken
from core.schemas.auth import (
    LoginRequest, LoginResponse, TokenResponse,
    MfaVerifyRequest, MfaSetupResponse, MfaConfirmRequest, MfaDisableRequest,
    AzureCallbackRequest,
)
from core.schemas.user import UserMe
from core.security import verify_password

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_KEY = "refresh_token"
_COOKIE_PATH = "/api/auth"

# ---------------------------------------------------------------------------
# In-memory replay prevention (safe for single-worker deployments)
# For multi-worker, replace with Redis SETNX with TTL.
# ---------------------------------------------------------------------------

_totp_lock = threading.Lock()
_used_totp: dict[str, float] = {}          # f"{user_id}:{code}" → expiry timestamp

_mfa_jti_lock = threading.Lock()
_used_mfa_jtis: dict[str, float] = {}      # jti → expiry timestamp


def _totp_is_fresh(user_id: int, code: str) -> bool:
    """Return True and mark code used if not seen in the last 90 s. False = replay."""
    key = f"{user_id}:{code}"
    now = time.monotonic()
    with _totp_lock:
        expired = [k for k, exp in _used_totp.items() if exp <= now]
        for k in expired:
            del _used_totp[k]
        if key in _used_totp:
            return False
        _used_totp[key] = now + 90  # ±1 TOTP window = 90 s
    return True


def _mfa_jti_consume(jti: str) -> bool:
    """Return True and mark JTI used if first use. False = already consumed."""
    now = time.monotonic()
    with _mfa_jti_lock:
        expired = [k for k, exp in _used_mfa_jtis.items() if exp <= now]
        for k in expired:
            del _used_mfa_jtis[k]
        if jti in _used_mfa_jtis:
            return False
        _used_mfa_jtis[jti] = now + MFA_TOKEN_EXPIRE_MINUTES * 60
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_KEY,
        value=token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE_KEY, path=_COOKIE_PATH)


def _issue_tokens(user: User, response: Response, db: Session) -> TokenResponse:
    """Create access + refresh tokens, persist the refresh JTI, set cookie."""
    client_ids = [uc.client_id for uc in user.user_clients]
    access_token = create_access_token(
        user.id, user.email, user.role, client_ids,
        must_change_password=user.must_change_password,
        mfa_setup_required=mfa_required_for_user(user, db) and not user.mfa_enabled,
    )
    refresh_token, jti = create_refresh_token(user.id)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=refresh_token_expires_at()))
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


def _verify_totp(user: User, code: str) -> bool:
    """
    Validate a TOTP code against the user's stored secret, with replay prevention.
    Returns False if the code is invalid OR if it has already been used in this window.
    """
    import pyotp
    if not user.mfa_secret:
        return False
    secret = decrypt(user.mfa_secret)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return False
    # Reject replays within the 90-second acceptance window
    return _totp_is_fresh(user.id, code)


# ── Login ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email, is_active=True).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.mfa_enabled:
        token, _jti = create_mfa_token(user.id)
        return LoginResponse(mfa_required=True, mfa_token=token)

    tokens = _issue_tokens(user, response, db)
    return LoginResponse(access_token=tokens.access_token)


# ── MFA verification (completes login) ──────────────────────────────────────

@router.post("/mfa/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
def mfa_verify(request: Request, body: MfaVerifyRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user_id, jti = verify_mfa_token(body.mfa_token)
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA session")

    # Enforce single-use: reject replayed mfa_tokens
    if not _mfa_jti_consume(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA session already used")

    user = db.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not _verify_totp(user, body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticator code")

    return _issue_tokens(user, response, db)


# ── MFA setup (authenticated — generates secret + QR code) ──────────────────

@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import pyotp
    import qrcode

    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="MFA is already enabled — disable it first to re-enrol")

    # Clear any previously unconfirmed secret before generating a new one.
    # This prevents stale secrets lingering and fixes the concurrent-setup race.
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.email, issuer_name="DMARC Intelligence")

    current_user.mfa_secret = encrypt(secret)
    db.commit()

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    return MfaSetupResponse(otpauth_uri=uri, qr_data_uri=qr_data_uri)


# ── MFA confirm (validates first code → enables MFA) ────────────────────────

@router.post("/mfa/confirm", response_model=TokenResponse)
@limiter.limit("5/minute")
def mfa_confirm(
    request: Request,
    body: MfaConfirmRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is already enabled")
    if not current_user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No MFA secret found — call /auth/mfa/setup first")

    if not _verify_totp(current_user, body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid code — check your authenticator app and try again")

    current_user.mfa_enabled = True
    db.commit()
    log.info("MFA enabled for user %d (%s)", current_user.id, current_user.email)

    # Re-issue tokens immediately so the new access token reflects mfa_enabled=True.
    # This clears the msr claim so the middleware stops blocking after enrolment.
    return _issue_tokens(current_user, response, db)


# ── MFA disable ──────────────────────────────────────────────────────────────

@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def mfa_disable(
    request: Request,
    body: MfaDisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if mfa_required_for_user(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA is enforced for your account — contact a super admin to reset your MFA device",
        )
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")

    if not _verify_totp(current_user, body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid code — MFA not disabled")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    db.commit()
    log.info("MFA disabled for user %d (%s)", current_user.id, current_user.email)


# ── Refresh ──────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(_COOKIE_KEY)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        user_id, jti = verify_refresh_token(token)
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    stored = db.query(RefreshToken).filter_by(jti=jti).first()
    if not stored or stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired or revoked")

    db.delete(stored)

    user = db.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return _issue_tokens(user, response, db)


# ── Logout ───────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(_COOKIE_KEY)
    if token:
        try:
            _, jti = verify_refresh_token(token)
            db.query(RefreshToken).filter_by(jti=jti).delete()
            db.commit()
        except (PyJWTError, Exception):
            pass
    _clear_refresh_cookie(response)


# ── /me ──────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMe)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from core.schemas.user import ClientRoleEntry
    client_roles = [
        ClientRoleEntry(slug=uc.client.slug, role=uc.role)
        for uc in current_user.user_clients
    ]
    mfa_req = mfa_required_for_user(current_user, db)
    return UserMe(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        must_change_password=current_user.must_change_password,
        has_password=current_user.password_hash is not None,
        mfa_enabled=current_user.mfa_enabled,
        mfa_setup_required=mfa_req and not current_user.mfa_enabled,
        mfa_required=mfa_req,
        created_at=current_user.created_at,
        client_slugs=[cr.slug for cr in client_roles],
        client_roles=client_roles,
    )


# ── Azure SSO ─────────────────────────────────────────────────────────────────

@router.get("/azure/login")
def azure_login(db: Session = Depends(get_db)):
    from api.auth.azure import get_auth_url
    if not settings.azure_client_id:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Azure SSO not configured")
    auth_url, state = get_auth_url(db)
    return {"auth_url": auth_url, "state": state}


@router.post("/azure/callback", response_model=TokenResponse)
def azure_callback(body: AzureCallbackRequest, response: Response, db: Session = Depends(get_db)):
    from api.auth.azure import exchange_code
    try:
        claims = exchange_code(body.code, body.state, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    user = db.query(User).filter_by(azure_oid=claims["oid"]).first()
    if not user:
        user = db.query(User).filter_by(email=claims["email"]).first()
        if user:
            user.azure_oid = claims["oid"]
        else:
            if not settings.azure_auto_provision:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account not found — contact your administrator",
                )
            user = User(email=claims["email"], role=UserRole.user.value, azure_oid=claims["oid"])
            db.add(user)
    db.commit()
    db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return _issue_tokens(user, response, db)