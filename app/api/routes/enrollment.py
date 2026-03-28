import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import EnrollmentToken, Tenant
from app.core.deps import get_current_tenant
from app.mdm.apple.profiles import build_mdm_enrollment_profile
from app.core.config import get_settings

router = APIRouter(prefix="/enrollment")
settings = get_settings()


class CreateTokenRequest(BaseModel):
    platform: str = "macos"
    reusable: bool = False
    expires_in_hours: int = 72


class TokenResponse(BaseModel):
    token: str
    platform: str
    reusable: bool
    expires_at: datetime | None
    enrollment_url: str


@router.post("/tokens", response_model=TokenResponse)
async def create_enrollment_token(
    body: CreateTokenRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    token_str = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)
    record = EnrollmentToken(
        tenant_id=tenant.id,
        token=token_str,
        platform=body.platform,
        reusable=body.reusable,
        expires_at=expires_at,
    )
    db.add(record)
    return TokenResponse(
        token=token_str,
        platform=body.platform,
        reusable=body.reusable,
        expires_at=expires_at,
        enrollment_url=f"/api/v1/enrollment/{token_str}",
    )


@router.get("/{token}")
async def download_enrollment_profile(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EnrollmentToken).where(EnrollmentToken.token == token)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Enrollment token not found")
    if record.used and not record.reusable:
        raise HTTPException(status_code=410, detail="Enrollment token already used")
    if record.expires_at and record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Enrollment token expired")

    result2 = await db.execute(
        select(Tenant).where(Tenant.id == record.tenant_id)  # type: ignore[arg-type]
    )
    tenant = result2.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    push_topic = tenant.apns_push_topic or ""
    profile_xml = build_mdm_enrollment_profile(
        tenant=tenant,
        server_url=f"https://mdm.example.com/mdm/apple/connect",
        checkin_url=f"https://mdm.example.com/mdm/apple/checkin",
        push_topic=push_topic,
        identity_cert_uuid="00000000-0000-0000-0000-000000000000",
    )

    if not record.reusable:
        record.used = True

    return Response(
        content=profile_xml,
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": f'attachment; filename="enroll.mobileconfig"'},
    )
