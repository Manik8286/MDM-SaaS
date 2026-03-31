from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Profile, Device, MdmCommand, Tenant, User
from app.core.deps import get_current_tenant, get_current_user
from app.mdm.apple.profiles import build_psso_profile, PssoProfileOptions
from app.mdm.apple.commands import make_install_profile_command
from app.services.audit import write_audit

router = APIRouter(prefix="/profiles")


class ProfileResponse(BaseModel):
    id: str
    name: str
    type: str
    platform: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateProfileRequest(BaseModel):
    name: str
    type: str
    platform: str = "macos"
    payload: dict = {}


class PssoProfileRequest(BaseModel):
    auth_method: str = "UserSecureEnclaveKey"
    enable_create_user_at_login: bool = True
    registration_token: str = ""
    admin_groups: list[str] | None = None


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Profile).where(Profile.tenant_id == tenant.id))
    return result.scalars().all()


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(
    body: CreateProfileRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = Profile(
        tenant_id=tenant.id,
        name=body.name,
        type=body.type,
        platform=body.platform,
        payload=body.payload,
    )
    db.add(profile)
    await db.flush()
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.tenant_id == tenant.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.tenant_id == tenant.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.execute(
        delete(Profile).where(Profile.id == profile_id, Profile.tenant_id == tenant.id)
    )


@router.post("/psso", status_code=202)
async def push_psso_profile(
    body: PssoProfileRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build a PSSO .mobileconfig and queue InstallProfile for all enrolled devices."""
    options = PssoProfileOptions(
        auth_method=body.auth_method,
        enable_create_user_at_login=body.enable_create_user_at_login,
        registration_token=body.registration_token,
        admin_groups=body.admin_groups,
    )
    profile_xml = build_psso_profile(tenant, options)

    devices_result = await db.execute(
        select(Device).where(Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    devices = devices_result.scalars().all()

    command_uuids = []
    for device in devices:
        cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
        db.add(cmd)
        command_uuids.append(cmd.command_uuid)

    await write_audit(
        db, tenant.id, "profile.psso_push", "profile",
        actor_id=user.id,
        changes={"queued": len(command_uuids), "auth_method": body.auth_method},
        ip_address=request.client.host if request.client else None,
    )
    return {"queued": len(command_uuids), "command_uuids": command_uuids}


@router.post("/{profile_id}/push", status_code=202)
async def push_profile(
    profile_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Queue InstallProfile command for all enrolled devices."""
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.tenant_id == tenant.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    import plistlib
    profile_xml = plistlib.dumps(profile.payload)

    devices_result = await db.execute(
        select(Device).where(Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    devices = devices_result.scalars().all()

    command_uuids = []
    for device in devices:
        cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
        db.add(cmd)
        command_uuids.append(cmd.command_uuid)

    return {"queued": len(command_uuids), "command_uuids": command_uuids}
