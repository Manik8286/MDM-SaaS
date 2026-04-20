import hashlib
import hmac
import io
import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import pyotp
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Cookie
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from jose import jwt as jose_jwt
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.core.deps import get_current_user, bearer
from app.db.base import get_db
from app.db.models import Tenant, User, Device, RevokedToken
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
    requires_2fa: bool = False
    temp_token: str | None = None


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    # If 2FA is enabled, issue a short-lived temp token and prompt for TOTP
    if user.totp_enabled:
        temp = create_access_token(
            subject=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
            extra={"type": "2fa_pending"},
            expire_minutes=5,
        )
        return TokenResponse(access_token="", requires_2fa=True, temp_token=temp)

    token = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    await write_audit(
        db, user.tenant_id, "auth.login", "user",
        actor_id=user.id, resource_id=user.id,
        changes={"method": "password"},
        ip_address=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    credentials=Depends(bearer),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current JWT by storing its jti in the blocklist."""
    from app.core.security import decode_token
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti")
    if jti:
        exp_ts = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc)
        db.add(RevokedToken(jti=jti, user_id=user.id, expires_at=expires_at))
    await write_audit(
        db, user.tenant_id, "auth.logout", "user",
        actor_id=user.id, resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )


# ── TOTP 2FA endpoints ────────────────────────────────────────────────────────

class TotpValidateRequest(BaseModel):
    temp_token: str
    totp_code: str


class TotpEnableRequest(BaseModel):
    totp_code: str


class TotpDisableRequest(BaseModel):
    totp_code: str


@router.get("/2fa/setup")
async def setup_2fa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new TOTP secret (does not activate until /2fa/enable is called)."""
    secret = pyotp.random_base32()
    # Store the pending secret on the user (not yet enabled)
    user.totp_secret = secret
    await db.flush()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="MDM SaaS")

    # Generate SVG QR code
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    buf = io.BytesIO()
    img.save(buf)
    svg_data = buf.getvalue().decode()

    return {"secret": secret, "otpauth_url": uri, "qr_svg": svg_data}


@router.post("/2fa/enable")
async def enable_2fa(
    body: TotpEnableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a TOTP code against the pending secret and activate 2FA."""
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Call /2fa/setup first")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.totp_enabled = True
    await db.flush()
    return {"enabled": True}


@router.post("/2fa/disable")
async def disable_2fa(
    body: TotpDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code then disable 2FA."""
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.totp_enabled = False
    user.totp_secret = None
    await db.flush()
    return {"enabled": False}


@router.post("/2fa/validate", response_model=TokenResponse)
async def validate_2fa(
    body: TotpValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a 2fa_pending temp token + TOTP code for a full access token."""
    from app.core.security import decode_token
    try:
        payload = decode_token(body.temp_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired temp token")

    if payload.get("type") != "2fa_pending":
        raise HTTPException(status_code=400, detail="Not a 2FA pending token")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="User not found")

    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA not configured for this user")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

    # Revoke the temp token immediately
    jti = payload.get("jti")
    if jti:
        from datetime import timezone as tz
        exp_ts = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc)
        db.add(RevokedToken(jti=jti, user_id=user.id, expires_at=expires_at))

    token = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    await write_audit(
        db, user.tenant_id, "auth.login", "user",
        actor_id=user.id, resource_id=user.id,
        changes={"method": "password+totp"},
        ip_address=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=token)


# ── Entra ID SSO helpers ──────────────────────────────────────────────────────

def _make_state(nonce: str, dashboard_origin: str = "") -> str:
    payload = f"{nonce}|{dashboard_origin}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_state(state: str) -> tuple[bool, str]:
    """Returns (valid, dashboard_origin)."""
    try:
        payload, sig = state.rsplit(".", 1)
        expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False, ""
        parts = payload.split("|", 1)
        origin = parts[1] if len(parts) > 1 else ""
        return True, origin
    except Exception:
        return False, ""


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
async def sso_entra_login(request: Request, dashboard_origin: str = Query(default="")):
    """Redirect browser to Microsoft login page."""
    entra_tid, entra_cid, _ = _get_entra_config()
    nonce = secrets.token_urlsafe(16)
    # Embed the caller's dashboard origin in state so callback can redirect back to it
    origin = dashboard_origin or settings.dashboard_url.rstrip("/")
    state = _make_state(nonce, origin)
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
    valid, dashboard_origin = _verify_state(state)
    if not valid:
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

    # Use the origin embedded in state; fall back to configured DASHBOARD_URL
    dashboard_url = (dashboard_origin or settings.dashboard_url).rstrip("/")

    if not user:
        # Not in the users table — access denied
        log.warning("Entra SSO: unknown user %s — access denied", email)
        return RedirectResponse(f"{dashboard_url}/login?error=not_authorized")

    if user.role not in ("admin", "superadmin", "owner"):
        log.warning("Entra SSO: user %s has role=%s — dashboard access denied", email, user.role)
        return RedirectResponse(f"{dashboard_url}/login?error=not_authorized")

    if user.status != "active":
        return RedirectResponse(f"{dashboard_url}/login?error=inactive")

    jwt_token = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    await write_audit(
        db, user.tenant_id, "auth.login", "user",
        actor_id=user.id, resource_id=user.id,
        changes={"method": "entra_sso", "email": email},
        ip_address=request.client.host if request.client else None,
    )
    return RedirectResponse(f"{dashboard_url}/login?token={jwt_token}")


# ── Portal SSO ────────────────────────────────────────────────────────────────
# Users open the portal URL in their browser — no agent token needed.
# Flow: GET /portal → redirect to /auth/portal/login →
#       Microsoft login → /auth/portal/callback →
#       set httpOnly cookie → redirect back to /portal
#
# Cookie: mdm_portal_session = signed JWT (sub=email, portal=true)
# Portal reads cookie on every API call via get_portal_user() dep.

PORTAL_COOKIE = "mdm_portal_session"
PORTAL_STATE_PREFIX = "portal."


@router.get("/portal/login")
async def portal_sso_login(request: Request, next: str = Query(default="/api/v1/portal")):
    """Redirect user to Microsoft login for portal access."""
    entra_tid, entra_cid, _ = _get_entra_config()
    nonce = secrets.token_urlsafe(16)
    # Encode 'next' URL into state so callback can redirect back
    raw_state = f"{PORTAL_STATE_PREFIX}{nonce}|{next}"
    sig = hmac.new(settings.secret_key.encode(), raw_state.encode(), hashlib.sha256).hexdigest()
    state = f"{raw_state}.{sig}"

    server_url = settings.mdm_server_url.rstrip("/")
    callback_url = f"{server_url}/api/v1/auth/portal/callback"
    params = urlencode({
        "client_id": entra_cid,
        "response_type": "code",
        "redirect_uri": callback_url,
        "scope": "openid email profile",
        "state": state,
        "response_mode": "query",
        "prompt": "select_account",
    })
    return RedirectResponse(
        f"https://login.microsoftonline.com/{entra_tid}/oauth2/v2.0/authorize?{params}"
    )


@router.get("/portal/callback")
async def portal_sso_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Receive OAuth2 code from Microsoft, set portal session cookie."""
    # Verify state signature
    try:
        raw_state, sig = state.rsplit(".", 1)
        expected = hmac.new(settings.secret_key.encode(), raw_state.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        if not raw_state.startswith(PORTAL_STATE_PREFIX):
            raise ValueError
        # Extract next URL
        _, rest = raw_state.split(PORTAL_STATE_PREFIX, 1)
        _, next_url = rest.split("|", 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state — possible CSRF")

    entra_tid, entra_cid, entra_cs = _get_entra_config()
    server_url = settings.mdm_server_url.rstrip("/")
    callback_url = f"{server_url}/api/v1/auth/portal/callback"
    token_url = f"https://login.microsoftonline.com/{entra_tid}/oauth2/v2.0/token"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data={
            "client_id": entra_cid,
            "client_secret": entra_cs,
            "code": code,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        })

    if resp.status_code != 200:
        log.error("Portal Entra token exchange failed: %s", resp.text)
        raise HTTPException(status_code=502, detail="Microsoft login failed")

    tokens = resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="No ID token from Microsoft")

    claims = jose_jwt.get_unverified_claims(id_token)
    email = (claims.get("email") or claims.get("preferred_username") or "").lower().strip()
    upn = claims.get("preferred_username", email)
    display_name = claims.get("name", email)
    ms_tid = claims.get("tid", "")

    if not email:
        raise HTTPException(status_code=400, detail="No email in Microsoft token")

    # Resolve tenant from Entra tenant ID
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.entra_tenant_id == ms_tid).limit(1)
    )
    tenant = tenant_result.scalars().first()
    if not tenant and ms_tid == entra_tid:
        tenant_result2 = await db.execute(select(Tenant).limit(1))
        tenant = tenant_result2.scalars().first()
    if not tenant:
        server_url = settings.mdm_server_url.rstrip("/")
        return RedirectResponse(f"{server_url}/api/v1/portal?error=no_tenant")

    # Find device enrolled by this user (match by hostname UPN or logged-in user)
    device_result = await db.execute(
        select(Device).where(Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    devices = device_result.scalars().all()

    # Issue a signed portal session cookie (1 hour)
    session_token = create_access_token(
        subject=email,
        tenant_id=tenant.id,
        role="portal",
        extra={"upn": upn, "name": display_name},
    )

    await write_audit(
        db, tenant.id, "auth.portal_login", "user",
        changes={"email": email, "method": "entra_sso"},
        ip_address=request.client.host if request.client else None,
    )

    response = RedirectResponse(next_url, status_code=302)
    response.set_cookie(
        key=PORTAL_COOKIE,
        value=session_token,
        httponly=True,
        secure=not settings.environment == "development",
        samesite="lax",
        max_age=3600,  # 1 hour
        path="/",
    )
    return response


@router.get("/portal/logout")
async def portal_logout(request: Request):
    """Clear portal session cookie and redirect to login."""
    server_url = settings.mdm_server_url.rstrip("/")
    response = RedirectResponse(f"{server_url}/api/v1/auth/portal/login")
    response.delete_cookie(PORTAL_COOKIE, path="/")
    return response
