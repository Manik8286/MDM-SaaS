"""
Public self-serve tenant signup.

POST /api/v1/signup
- No auth required
- Creates Tenant (trial plan, 5-device limit, 14-day trial)
- Creates first User (role=owner)
- Returns a JWT so the user lands straight in the dashboard
"""
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.security import create_access_token, hash_password
from app.db.base import get_db
from app.db.models import Tenant, User

log = logging.getLogger(__name__)
router = APIRouter()

TRIAL_DAYS = 14
TRIAL_DEVICE_LIMIT = 5


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] or "org"


class SignupRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str

    @field_validator("org_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Organisation name is required")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class SignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    tenant_slug: str


@router.post("/signup", response_model=SignupResponse, status_code=201)
@limiter.limit("5/minute")
async def signup(body: SignupRequest, request, db: AsyncSession = Depends(get_db)):
    # Reject duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    # Generate a unique slug
    base_slug = _slugify(body.org_name)
    slug = base_slug
    suffix = 1
    while True:
        clash = await db.execute(select(Tenant).where(Tenant.slug == slug))
        if not clash.scalar_one_or_none():
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    trial_ends = datetime.utcnow() + timedelta(days=TRIAL_DAYS)

    tenant = Tenant(
        name=body.org_name.strip(),
        slug=slug,
        plan="trial",
        status="active",
        billing_status="trialing",
        plan_device_limit=TRIAL_DEVICE_LIMIT,
        trial_ends_at=trial_ends,
    )
    db.add(tenant)
    await db.flush()  # get tenant.id

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role="owner",
        status="active",
    )
    db.add(user)
    await db.flush()

    token = create_access_token(subject=user.id, tenant_id=tenant.id, role=user.role)

    log.info("New tenant signed up: slug=%s owner=%s", slug, body.email)

    return SignupResponse(
        access_token=token,
        tenant_id=tenant.id,
        tenant_slug=slug,
    )
