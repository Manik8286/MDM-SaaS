import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import EnrollmentToken, Tenant
from app.core.deps import get_current_tenant
import logging
import os
from app.mdm.apple.profiles import build_mdm_enrollment_profile, sign_profile

log = logging.getLogger(__name__)
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
    expires_at = datetime.utcnow() + timedelta(hours=body.expires_in_hours)
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
        enrollment_url=f"{settings.mdm_server_url.rstrip('/')}/api/v1/enrollment/{token_str}",
    )


@router.get("/{token}")
async def download_enrollment_profile(
    token: str,
    request: Request,
    download: bool = False,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EnrollmentToken).where(EnrollmentToken.token == token)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Enrollment token not found")
    if record.used and not record.reusable:
        raise HTTPException(status_code=410, detail="Enrollment token already used")
    if record.expires_at and record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Enrollment token expired")

    result2 = await db.execute(
        select(Tenant).where(Tenant.id == record.tenant_id)  # type: ignore[arg-type]
    )
    tenant = result2.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # If the request comes from a browser, serve an HTML landing page with an Install button.
    # mdmclient / curl sends Accept: */* or application/x-apple-aspen-config — serve profile directly.
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header and not download:
        base_url = str(request.url).split("?")[0]
        profile_url = f"{base_url}?download=1"
        html = _enrollment_landing_page(tenant.name, profile_url)
        return Response(content=html, media_type="text/html", headers={"ngrok-skip-browser-warning": "1"})

    # Build and optionally sign the .mobileconfig
    push_topic = tenant.apns_push_topic or f"com.mdmsaas.mdm.{tenant.slug}"
    base_url = settings.mdm_server_url.rstrip("/")
    profile_xml = build_mdm_enrollment_profile(
        tenant=tenant,
        server_url=f"{base_url}/mdm/apple/connect",
        checkin_url=f"{base_url}/mdm/apple/checkin",
        push_topic=push_topic,
    )

    cert_path = settings.mdm_signing_cert_path
    key_path = settings.mdm_signing_key_path
    if cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path):
        try:
            profile_xml = sign_profile(profile_xml, cert_path, key_path)
            log.info("Enrollment profile signed with %s", cert_path)
        except Exception as e:
            log.warning("Profile signing failed, serving unsigned: %s", e)

    if not record.reusable:
        record.used = True

    return Response(
        content=profile_xml,
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": 'attachment; filename="enroll.mobileconfig"'},
    )


def _enrollment_landing_page(org_name: str, profile_url: str) -> str:
    """Simple HTML page shown when a browser opens an enrollment link."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Enroll in {org_name} MDM</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f7;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; padding: 24px;
    }}
    .card {{
      background: white; border-radius: 18px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      padding: 48px 40px; max-width: 420px; width: 100%; text-align: center;
    }}
    .icon {{ font-size: 52px; margin-bottom: 20px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #1d1d1f; margin-bottom: 8px; }}
    .org {{ font-size: 15px; color: #6e6e73; margin-bottom: 28px; }}
    .steps {{
      text-align: left; background: #f5f5f7; border-radius: 12px;
      padding: 20px 24px; margin-bottom: 28px;
    }}
    .steps p {{ font-size: 13px; font-weight: 600; color: #6e6e73;
      text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }}
    .steps ol {{ padding-left: 18px; }}
    .steps li {{ font-size: 14px; color: #1d1d1f; margin-bottom: 6px; line-height: 1.5; }}
    .btn {{
      display: inline-block; background: #0071e3; color: white;
      font-size: 16px; font-weight: 600; padding: 14px 32px;
      border-radius: 980px; text-decoration: none; width: 100%;
      transition: background 0.15s;
    }}
    .btn:hover {{ background: #0077ed; }}
    .note {{ font-size: 12px; color: #aeaeb2; margin-top: 18px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🔒</div>
    <h1>Device Enrollment</h1>
    <p class="org">{org_name}</p>

    <div class="steps">
      <p>How it works</p>
      <ol>
        <li>Click <strong>Install Profile</strong> below</li>
        <li>Open <strong>System Settings → Privacy &amp; Security → Profiles</strong></li>
        <li>Click the downloaded profile and tap <strong>Install</strong></li>
        <li>Enter your Mac password to confirm</li>
      </ol>
    </div>

    <a href="{profile_url}" class="btn">Install Profile</a>
    <p class="note">This will enroll your Mac into {org_name}&apos;s device management system.</p>
  </div>
</body>
</html>"""
