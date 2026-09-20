"""
Public self-serve tenant signup.

POST /api/v1/signup
- No auth required
- Creates Tenant in a "pending" billing state (no devices allowed yet) and
  the first User (role=owner)
- Returns a JWT immediately so the frontend can call POST /billing/checkout
  next, which starts a 5-day Stripe trial on the chosen plan. The tenant is
  only activated (device limit unlocked) once the Stripe webhook confirms
  the checkout session / subscription — see app/api/routes/billing.py
"""
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.security import create_access_token, hash_password
from app.db.base import get_db
from app.db.models import Tenant, User
from app.services.email import send_welcome_email

log = logging.getLogger(__name__)
router = APIRouter()


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] or "org"


class SignupRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str
    plan: Literal["starter", "professional"] = "starter"

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
    plan: str


@router.post("/signup", response_model=SignupResponse, status_code=201)
@limiter.limit("5/minute")
async def signup(body: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
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

    # Tenant starts "pending" — no devices can be enrolled until the Stripe
    # checkout (started right after this call returns) confirms the card and
    # the webhook activates the plan with its 5-day trial.
    tenant = Tenant(
        name=body.org_name.strip(),
        slug=slug,
        plan=body.plan,
        status="active",
        billing_status="pending",
        plan_device_limit=0,
        trial_ends_at=None,
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

    log.info("New tenant signed up: slug=%s owner=%s plan=%s", slug, body.email, body.plan)

    await send_welcome_email(body.email, tenant.name)

    return SignupResponse(
        access_token=token,
        tenant_id=tenant.id,
        tenant_slug=slug,
        plan=body.plan,
    )
