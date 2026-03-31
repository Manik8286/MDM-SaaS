"""
Patch management and compliance API.
Endpoints for installed apps, OS updates, compliance status, and triggering scans.
"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, Tenant, InstalledApp, DeviceUpdate
from app.core.deps import get_current_tenant
from app.mdm.apple.commands import (
    make_installed_app_list_command,
    make_available_os_updates_command,
    make_schedule_os_update_scan_command,
    make_schedule_os_update_command,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class InstalledAppResponse(BaseModel):
    name: str
    bundle_id: str | None
    version: str | None
    short_version: str | None
    source: str | None
    last_seen_at: datetime
    model_config = {"from_attributes": True}


class DeviceUpdateResponse(BaseModel):
    product_key: str
    human_readable_name: str | None
    version: str | None
    build: str | None
    is_critical: bool
    restart_required: bool
    last_seen_at: datetime
    model_config = {"from_attributes": True}


class ComplianceResponse(BaseModel):
    compliance_status: str
    compliance_checked_at: datetime | None
    is_encrypted: bool | None
    is_supervised: bool | None
    critical_update_count: int
    total_update_count: int
    total_app_count: int


class ScanRequest(BaseModel):
    force: bool = False


class InstallUpdateRequest(BaseModel):
    product_keys: list[str]
    install_action: str = "InstallLater"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_device(device_id: str, tenant: Tenant, db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


async def _push_device(device: Device) -> None:
    if not device.push_token or not device.push_magic or not device.push_topic:
        return
    try:
        from app.mdm.apple.apns import send_mdm_push
        await send_mdm_push(
            push_token_hex=device.push_token,
            push_magic=device.push_magic,
            push_topic=device.push_topic,
        )
    except Exception as e:
        log.warning("APNs push failed for device %s: %s", device.id, e)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/devices/{device_id}/patch/apps", response_model=list[InstalledAppResponse])
async def get_installed_apps(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _get_device(device_id, tenant, db)
    result = await db.execute(
        select(InstalledApp)
        .where(InstalledApp.device_id == device_id)
        .order_by(InstalledApp.name.asc())
    )
    return result.scalars().all()


@router.get("/devices/{device_id}/patch/updates", response_model=list[DeviceUpdateResponse])
async def get_available_updates(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _get_device(device_id, tenant, db)
    result = await db.execute(
        select(DeviceUpdate)
        .where(DeviceUpdate.device_id == device_id)
        .order_by(DeviceUpdate.is_critical.desc(), DeviceUpdate.human_readable_name.asc())
    )
    return result.scalars().all()


@router.get("/devices/{device_id}/patch/compliance", response_model=ComplianceResponse)
async def get_compliance(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)

    critical_count = await db.scalar(
        select(func.count()).select_from(DeviceUpdate)
        .where(DeviceUpdate.device_id == device_id, DeviceUpdate.is_critical == True)
    ) or 0

    total_updates = await db.scalar(
        select(func.count()).select_from(DeviceUpdate)
        .where(DeviceUpdate.device_id == device_id)
    ) or 0

    total_apps = await db.scalar(
        select(func.count()).select_from(InstalledApp)
        .where(InstalledApp.device_id == device_id)
    ) or 0

    return ComplianceResponse(
        compliance_status=device.compliance_status,
        compliance_checked_at=device.compliance_checked_at,
        is_encrypted=device.is_encrypted,
        is_supervised=device.is_supervised,
        critical_update_count=critical_count,
        total_update_count=total_updates,
        total_app_count=total_apps,
    )


@router.post("/devices/{device_id}/patch/scan", status_code=202)
async def scan_device(
    device_id: str,
    body: ScanRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)

    cmds = [
        make_schedule_os_update_scan_command(device.id, tenant.id, force=body.force),
        make_available_os_updates_command(device.id, tenant.id),
        make_installed_app_list_command(device.id, tenant.id),
    ]
    for cmd in cmds:
        db.add(cmd)

    asyncio.create_task(_push_device(device))
    return {"queued": len(cmds), "command_uuids": [c.command_uuid for c in cmds]}


@router.post("/devices/{device_id}/patch/install", status_code=202)
async def install_updates(
    device_id: str,
    body: InstallUpdateRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)

    # Validate all product_keys exist for this device
    result = await db.execute(
        select(DeviceUpdate.product_key)
        .where(DeviceUpdate.device_id == device_id, DeviceUpdate.product_key.in_(body.product_keys))
    )
    found_keys = {row[0] for row in result.fetchall()}
    unknown = set(body.product_keys) - found_keys
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown product keys: {sorted(unknown)}")

    updates_payload = [
        {"ProductKey": key, "InstallAction": body.install_action}
        for key in body.product_keys
    ]
    cmd = make_schedule_os_update_command(device.id, tenant.id, updates=updates_payload)
    db.add(cmd)
    asyncio.create_task(_push_device(device))
    return {"command_uuid": cmd.command_uuid}
