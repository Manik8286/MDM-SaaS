import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.base import get_db
from app.db.models import Tenant, User
from app.services.audit import write_audit

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")
    token = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    await write_audit(
        db, user.tenant_id, "auth.login", "user",
        actor_id=user.id, resource_id=user.id,
        changes={"method": "password"},
        ip_address=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=token)


# ── Entra ID SSO helpers ──────────────────────────────────────────────────────

def _make_state(nonce: str) -> str:
    sig = hmac.new(settings.secret_key.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def _verify_state(state: str) -> bool:
    try:
        nonce, sig = state.rsplit(".", 1)
        expected = hmac.new(settings.secret_key.encode(), nonce.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def _get_entra_config() -> tuple[str, str, str]:
    """Return (tenant_id, client_id, client_secret) from env or raise 400."""
    tid = settings.entra_tenant_id
    cid = settings.entra_client_id
    cs = settings.entra_client_secret
    if not tid or not cid or not cs:
        raise HTTPException(
            status_code=400,
            detail="Entra SSO is not configured. Set ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET in .env",
        )
    return tid, cid, cs


# ── GET /auth/sso/entra/login ─────────────────────────────────────────────────

@router.get("/sso/entra/login")
async def sso_entra_login():
    """Redirect browser to Microsoft login page."""
    entra_tid, entra_cid, _ = _get_entra_config()
    nonce = secrets.token_urlsafe(16)
    state = _make_state(nonce)
    callback_url = settings.entra_redirect_uri or f"{settings.mdm_server_url.rstrip('/')}/api/v1/auth/sso/entra/callback"
    params = urlencode({
        "client_id": entra_cid,
        "response_type": "code",
        "redirect_uri": callback_url,
        "scope": "openid email profile",
        "state": state,
        "response_mode": "query",
        "prompt": "select_account",
    })
    authorize_url = f"https://login.microsoftonline.com/{entra_tid}/oauth2/v2.0/authorize?{params}"
    return RedirectResponse(authorize_url)


# ── GET /auth/sso/entra/callback ──────────────────────────────────────────────

@router.get("/sso/entra/callback")
async def sso_entra_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Receive OAuth2 code from Microsoft, exchange for tokens, issue JWT."""
    if not _verify_state(state):
        raise HTTPException(status_code=400, detail="Invalid state — possible CSRF")

    entra_tid, entra_cid, entra_cs = _get_entra_config()
    callback_url = settings.entra_redirect_uri or f"{settings.mdm_server_url.rstrip('/')}/api/v1/auth/sso/entra/callback"
    token_url = f"https://login.microsoftonline.com/{entra_tid}/oauth2/v2.0/token"

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data={
            "client_id": entra_cid,
            "client_secret": entra_cs,
            "code": code,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        })

    if resp.status_code != 200:
        log.error("Entra token exchange failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="Token exchange with Microsoft failed")

    tokens = resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="No ID token in Microsoft response")

    # Decode claims — we trust them because we just fetched them directly from Microsoft
    claims = jose_jwt.get_unverified_claims(id_token)
    email = (claims.get("email") or claims.get("preferred_username") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="No email claim in ID token")

    # Find existing user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision: find tenant by Entra tenant OID (the `tid` claim)
        ms_tid = claims.get("tid", "")
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.entra_tenant_id == ms_tid)
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            # Fall back to global entra_tenant_id match
            if ms_tid == entra_tid:
                # Find first active tenant (single-tenant dev mode)
                tenant_result2 = await db.execute(select(Tenant).limit(1))
                tenant = tenant_result2.scalar_one_or_none()
        if not tenant:
            log.warning("Entra SSO: no tenant for tid=%s email=%s", ms_tid, email)
            dashboard_url = settings.dashboard_url.rstrip("/")
            return RedirectResponse(
                f"{dashboard_url}/login?error=no_tenant"
            )
        user = User(
            tenant_id=tenant.id,
            email=email,
            role="admin",
            status="active",
        )
        db.add(user)
        await db.flush()
        log.info("Entra SSO: auto-provisioned user %s in tenant %s", email, tenant.id)

    if user.status != "active":
        dashboard_url = settings.dashboard_url.rstrip("/")
        return RedirectResponse(f"{dashboard_url}/login?error=inactive")

    jwt_token = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    await write_audit(
        db, user.tenant_id, "auth.login", "user",
        actor_id=user.id, resource_id=user.id,
        changes={"method": "entra_sso", "email": email},
        ip_address=request.client.host if request.client else None,
    )
    dashboard_url = settings.dashboard_url.rstrip("/")
    return RedirectResponse(f"{dashboard_url}/login?token={jwt_token}")
