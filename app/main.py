"""
MDM SaaS — FastAPI application entry point.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.limiter import limiter
from app.middleware.logging import configure_logging, RequestIdMiddleware
from app.db.base import engine
from app.db.models import Base
from app.mdm.apple.checkin import router as checkin_router
from app.mdm.apple.connect import router as connect_router
from app.mdm.windows.enrollment import router as win_enrollment_router
from app.mdm.windows.omadm import router as win_omadm_router
from app.api.routes.auth import router as auth_router
from app.api.routes.tenant import router as tenant_router
from app.api.routes.devices import router as devices_router
from app.api.routes.enrollment import router as enrollment_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.patch import router as patch_router
from app.api.routes.audit import router as audit_router
from app.api.routes.compliance import router as compliance_router
from app.api.routes.admin_access import router as admin_access_router
from app.api.routes.agent import router as agent_router
from app.api.routes.portal import router as portal_router
from app.api.routes.packages import router as packages_router
from app.api.routes.users import router as users_router
from app.api.routes.groups import router as groups_router
from app.api.routes.signup import router as signup_router
from app.api.routes.billing import router as billing_router

settings = get_settings()
configure_logging(level=settings.log_level, json_logs=settings.is_production)
log = logging.getLogger(__name__)


def _run_migrations() -> None:
    """
    Run alembic upgrade head in a subprocess.

    We cannot call alembic_command.upgrade() directly here because env.py uses
    asyncio.run(), which raises RuntimeError when a loop is already running
    (FastAPI's lifespan context). A subprocess gets its own clean event loop.
    """
    import subprocess
    import sys
    import os

    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", os.path.abspath(ini_path), "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            log.info("alembic: %s", line)
    if result.returncode != 0:
        log.error("Alembic migration failed:\n%s", result.stderr)
        raise RuntimeError("Alembic migration failed — startup aborted")
    log.info("Alembic migrations applied")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting MDM SaaS API (env=%s)", settings.environment)

    # Run migrations first, then let create_all handle any tables not yet in Alembic
    _run_migrations()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.services.auto_revoke import auto_revoke_loop
    revoke_task = asyncio.create_task(auto_revoke_loop())

    yield

    revoke_task.cancel()
    await engine.dispose()
    log.info("API shutdown complete")


app = FastAPI(
    title="MDM SaaS API",
    version="0.1.0",
    description="Multi-tenant MDM for Mac and Windows with Entra ID PSSO",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [settings.dashboard_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error: %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Apple MDM protocol endpoints (device-facing, mTLS auth)
app.include_router(checkin_router, tags=["MDM Apple"])
app.include_router(connect_router, tags=["MDM Apple"])

# Windows MDM protocol endpoints (MS-MDE2 enrollment + OMA-DM) — disabled (Phase 2)
# app.include_router(win_enrollment_router, tags=["MDM Windows"])
# app.include_router(win_omadm_router, tags=["MDM Windows"])

# Dashboard API endpoints (JWT auth)
app.include_router(auth_router,       prefix="/api/v1", tags=["Auth"])
app.include_router(tenant_router,     prefix="/api/v1", tags=["Tenant"])
app.include_router(devices_router,    prefix="/api/v1", tags=["Devices"])
app.include_router(enrollment_router, prefix="/api/v1", tags=["Enrollment"])
app.include_router(profiles_router,   prefix="/api/v1", tags=["Profiles"])
app.include_router(patch_router,      prefix="/api/v1", tags=["Patch"])
app.include_router(audit_router,      prefix="/api/v1", tags=["Audit"])
app.include_router(compliance_router,   prefix="/api/v1", tags=["Compliance"])
app.include_router(admin_access_router, prefix="/api/v1", tags=["Admin Access"])
app.include_router(agent_router,        prefix="/api/v1", tags=["Agent"])
app.include_router(portal_router,       prefix="/api/v1", tags=["Portal"])
app.include_router(packages_router,     prefix="/api/v1", tags=["Packages"])
app.include_router(users_router,        prefix="/api/v1", tags=["Users"])
app.include_router(groups_router,       prefix="/api/v1", tags=["Groups"])
app.include_router(signup_router,       prefix="/api/v1", tags=["Signup"])
app.include_router(billing_router,      prefix="/api/v1", tags=["Billing"])


@app.get("/healthz", tags=["Health"])
async def health():
    return {"status": "ok", "env": settings.environment}


@app.get("/readyz", tags=["Health"])
async def ready():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not ready", "detail": str(e)})
