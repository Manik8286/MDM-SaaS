from fastapi import Depends, HTTPException, status, Cookie, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_db
from app.db.models import User, Tenant, RevokedToken
from app.core.security import decode_token
from typing import Optional

bearer = HTTPBearer()

PORTAL_COOKIE = "mdm_portal_session"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Check token revocation blocklist
    jti = payload.get("jti")
    if jti:
        revoked = await db.execute(select(RevokedToken).where(RevokedToken.jti == jti))
        if revoked.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_tenant(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not active")
    return tenant


class PortalSession:
    """Decoded portal session — identifies the logged-in user by email + tenant."""
    def __init__(self, email: str, tenant_id: str, display_name: str, upn: str):
        self.email = email
        self.tenant_id = tenant_id
        self.display_name = display_name
        self.upn = upn


async def get_portal_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalSession:
    """
    Validate the portal session cookie.
    If missing or invalid, redirect to Entra login.
    """
    token = request.cookies.get(PORTAL_COOKIE)
    if not token:
        next_url = str(request.url)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="portal_login_required",
            headers={"X-Portal-Login-URL": f"/api/v1/auth/portal/login?next={next_url}"},
        )
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="portal_login_required",
        )
    if payload.get("role") != "portal":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a portal session")

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == payload["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not active")

    return PortalSession(
        email=payload["sub"],
        tenant_id=payload["tenant_id"],
        display_name=payload.get("name", payload["sub"]),
        upn=payload.get("upn", payload["sub"]),
    )
