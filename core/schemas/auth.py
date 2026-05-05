from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Returned by POST /auth/login. Either issues tokens or signals MFA is required."""
    # Normal path — access token present, mfa_required is False
    access_token: str | None = None
    token_type: str = "bearer"
    # MFA path — mfa_required is True, mfa_token is a short-lived intermediate JWT
    mfa_required: bool = False
    mfa_token: str | None = None


class TokenResponse(BaseModel):
    """Returned after full authentication (no MFA pending)."""
    access_token: str
    token_type: str = "bearer"
    # refresh_token is now an HttpOnly cookie — not included in the response body


class MfaVerifyRequest(BaseModel):
    mfa_token: str   # the intermediate JWT from /auth/login
    code: str        # 6-digit TOTP code


class MfaSetupResponse(BaseModel):
    otpauth_uri: str   # scanned by the authenticator app
    qr_data_uri: str   # data:image/png;base64,... for the frontend to render


class MfaConfirmRequest(BaseModel):
    code: str   # first TOTP code — proves the app is correctly configured


class MfaDisableRequest(BaseModel):
    code: str   # current TOTP code — proves user still has access to the device


class RefreshRequest(BaseModel):
    refresh_token: str


class AzureCallbackRequest(BaseModel):
    code: str
    state: str