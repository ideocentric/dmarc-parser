from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from api.limiter import limiter

from core.config import settings
from core.database import init_db
from api.routes.auth import router as auth_router
from api.routes.users import router as users_router
from api.routes.clients import router as clients_router
from api.routes.reports import router as reports_router, records_router
from api.routes.flags import router as flags_router
from api.routes.analytics import router as analytics_router, cross_router
from api.routes.imap import router as imap_router

_scheduler = None

# Paths exempt from must-change-password enforcement
_MCP_EXEMPT_SUFFIXES = ("/change-password",)
_MCP_EXEMPT_PATHS = {"/auth/login", "/auth/refresh", "/auth/logout",
                      "/auth/me", "/auth/mfa/verify", "/health"}

# Paths exempt from MFA-setup enforcement (user must be able to complete enrolment)
_MSR_EXEMPT_PATHS = {"/auth/login", "/auth/refresh", "/auth/logout",
                     "/auth/me", "/auth/mfa/verify",
                     "/auth/mfa/setup", "/auth/mfa/confirm", "/health"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _scheduler
    from core.logging import configure_logging
    configure_logging()  # must run after uvicorn initialises to own the root handlers
    init_db()
    from ingestion.scheduler import start_scheduler
    _scheduler = start_scheduler()
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(
    title="DMARC Intelligence Platform",
    version="0.2.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_password_change(request: Request, call_next):
    """Block all endpoints (except a small whitelist) when must_change_password is set."""
    path = request.url.path
    if (path in _MCP_EXEMPT_PATHS
            or any(path.endswith(s) for s in _MCP_EXEMPT_SUFFIXES)
            or path.startswith("/auth/azure")):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from api.auth.jwt import decode_token
            payload = decode_token(auth_header.split(" ", 1)[1])
            if payload.get("mcp"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Password change required", "code": "password_change_required"},
                )
        except Exception:
            pass

    return await call_next(request)


@app.middleware("http")
async def enforce_mfa_setup(request: Request, call_next):
    """Block all endpoints (except a small whitelist) when MFA enrolment is pending.
    Runs before enforce_password_change (defined after = outermost in Starlette's LIFO stack)."""
    path = request.url.path
    if path in _MSR_EXEMPT_PATHS or path.startswith("/auth/azure"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from api.auth.jwt import decode_token
            payload = decode_token(auth_header.split(" ", 1)[1])
            if payload.get("msr"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "MFA setup required", "code": "mfa_setup_required"},
                )
        except Exception:
            pass

    return await call_next(request)


for r in (auth_router, users_router, clients_router, reports_router,
          records_router, flags_router, analytics_router, cross_router, imap_router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}