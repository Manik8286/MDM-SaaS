"""
MDM SaaS — FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
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

settings = get_settings()
logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting MDM SaaS API (env=%s)", settings.environment)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
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
