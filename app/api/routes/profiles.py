import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Profile, Device, MdmCommand, Tenant, User
from app.core.deps import get_current_tenant, get_current_user
from app.mdm.apple.profiles import (
    build_psso_profile, PssoProfileOptions,
    build_usb_block_profile, build_gatekeeper_profile,
    usb_block_profile_identifier,
    build_icloud_block_profile, icloud_block_profile_identifier,
    build_onedrive_kfm_profile, onedrive_kfm_profile_identifier,
)
from app.mdm.apple.commands import make_install_profile_command, make_remove_profile_command
from app.services.audit import write_audit

log = logging.getLogger(__name__)


async def _push_device(device: Device) -> None:
    if not device.push_token or not device.push_magic or not device.push_topic:
        log.info("Device %s has no push token — command queued, device will pick up on next poll", device.id)
        return
    try:
        from app.mdm.apple.apns import send_mdm_push
        await send_mdm_push(
            push_token_hex=device.push_token,
            push_magic=device.push_magic,
            push_topic=device.push_topic,
        )
        log.info("APNs push sent to device %s", device.id)
    except Exception as e:
        log.warning("APNs push failed for device %s (command still queued): %s", device.id, e)

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
    for device in devices:
        asyncio.create_task(_push_device(device))
    return {"queued": len(command_uuids), "command_uuids": command_uuids}


@router.post("/psso/push/{device_id}", status_code=202)
async def push_psso_profile_device(
    device_id: str,
    body: PssoProfileRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build a PSSO .mobileconfig and queue InstallProfile for a single device."""
    device_result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found or not enrolled")

    options = PssoProfileOptions(
        auth_method=body.auth_method,
        enable_create_user_at_login=body.enable_create_user_at_login,
        registration_token=body.registration_token,
        admin_groups=body.admin_groups,
    )
    profile_xml = build_psso_profile(tenant, options)
    cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "profile.psso_push", "profile",
        actor_id=user.id,
        changes={"device_id": device_id, "auth_method": body.auth_method},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"queued": 1, "command_uuid": cmd.command_uuid}


class GatekeeperPushRequest(BaseModel):
    allow_identified_developers: bool = True


@router.post("/usb-block/push", status_code=202)
async def push_usb_block(
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push USB storage block profile to all enrolled devices."""
    profile_xml = build_usb_block_profile(tenant)
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
        db, tenant.id, "policy.usb_block_push", "policy",
        actor_id=user.id,
        changes={"queued": len(command_uuids)},
        ip_address=request.client.host if request.client else None,
    )
    for device in devices:
        asyncio.create_task(_push_device(device))
    return {"queued": len(command_uuids), "command_uuids": command_uuids}


@router.post("/gatekeeper/push", status_code=202)
async def push_gatekeeper(
    body: GatekeeperPushRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push Gatekeeper enforcement profile to all enrolled devices."""
    profile_xml = build_gatekeeper_profile(tenant, body.allow_identified_developers)
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
        db, tenant.id, "policy.gatekeeper_push", "policy",
        actor_id=user.id,
        changes={"queued": len(command_uuids), "allow_identified_developers": body.allow_identified_developers},
        ip_address=request.client.host if request.client else None,
    )
    for device in devices:
        asyncio.create_task(_push_device(device))
    return {"queued": len(command_uuids), "command_uuids": command_uuids}


@router.post("/icloud-block/push", status_code=202)
async def push_icloud_block(
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push iCloud block profile to all enrolled devices."""
    profile_xml = build_icloud_block_profile(tenant)
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
        db, tenant.id, "policy.icloud_block_push", "policy",
        actor_id=user.id,
        changes={"queued": len(command_uuids)},
        ip_address=request.client.host if request.client else None,
    )
    for device in devices:
        asyncio.create_task(_push_device(device))
    return {"queued": len(command_uuids), "command_uuids": command_uuids}


@router.post("/icloud-block/push/{device_id}", status_code=202)
async def push_icloud_block_device(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push iCloud block profile to a single device."""
    device_result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found or not enrolled")
    profile_xml = build_icloud_block_profile(tenant)
    cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "policy.icloud_block_push", "policy",
        actor_id=user.id,
        changes={"device_id": device_id},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"queued": 1, "command_uuid": cmd.command_uuid}


@router.post("/icloud-block/remove/{device_id}", status_code=202)
async def remove_icloud_block_device(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove iCloud block profile from a single device."""
    device_result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    cmd = make_remove_profile_command(device.id, tenant.id, icloud_block_profile_identifier(tenant.id))
    db.add(cmd)
    await write_audit(
        db, tenant.id, "policy.icloud_block_remove", "policy",
        actor_id=user.id,
        changes={"device_id": device_id},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"queued": 1, "command_uuid": cmd.command_uuid}


class OneDriveKFMRequest(BaseModel):
    entra_tenant_id: str = ""


@router.post("/onedrive-kfm/push", status_code=202)
async def push_onedrive_kfm(
    body: OneDriveKFMRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push OneDrive KFM profile to all enrolled devices."""
    entra_tid = body.entra_tenant_id or tenant.entra_tenant_id or ""
    if not entra_tid:
        raise HTTPException(status_code=400, detail="Entra tenant ID required for OneDrive KFM")
    profile_xml = build_onedrive_kfm_profile(tenant, entra_tid)
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
        db, tenant.id, "policy.onedrive_kfm_push", "policy",
        actor_id=user.id,
        changes={"queued": len(command_uuids)},
        ip_address=request.client.host if request.client else None,
    )
    for device in devices:
        asyncio.create_task(_push_device(device))
    return {"queued": len(command_uuids), "command_uuids": command_uuids}


@router.post("/onedrive-kfm/push/{device_id}", status_code=202)
async def push_onedrive_kfm_device(
    device_id: str,
    body: OneDriveKFMRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push OneDrive KFM profile to a single device."""
    device_result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found or not enrolled")
    entra_tid = body.entra_tenant_id or tenant.entra_tenant_id or ""
    if not entra_tid:
        raise HTTPException(status_code=400, detail="Entra tenant ID required for OneDrive KFM")
    profile_xml = build_onedrive_kfm_profile(tenant, entra_tid)
    cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "policy.onedrive_kfm_push", "policy",
        actor_id=user.id,
        changes={"device_id": device_id},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"queued": 1, "command_uuid": cmd.command_uuid}


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


@router.post("/usb-block/push/{device_id}", status_code=202)
async def push_usb_block_device(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push USB storage block profile to a specific device."""
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    profile_xml = build_usb_block_profile(tenant)
    cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "policy.usb_block_push", "policy",
        actor_id=user.id,
        changes={"device_id": device_id, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"queued": 1, "command_uuids": [cmd.command_uuid]}


@router.post("/usb-block/remove/{device_id}", status_code=202)
async def remove_usb_block_device(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove USB block profile from a specific device."""
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    command_uuids = []
    # Use the deterministic top-level profile identifier — RemoveProfile targets
    # the outer PayloadIdentifier, not the inner payload identifiers.
    cmd = make_remove_profile_command(device.id, tenant.id, usb_block_profile_identifier(tenant.id))
    db.add(cmd)
    command_uuids.append(cmd.command_uuid)

    await write_audit(
        db, tenant.id, "policy.usb_block_remove", "policy",
        actor_id=user.id,
        changes={"device_id": device_id, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"queued": len(command_uuids), "command_uuids": command_uuids}
