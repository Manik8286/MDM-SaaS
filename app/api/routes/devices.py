from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, MdmCommand, Tenant
from app.core.deps import get_current_tenant
from app.mdm.apple.commands import (
    make_device_lock_command, make_erase_device_command,
    make_restart_command, make_device_information_command,
)

router = APIRouter(prefix="/devices")


class DeviceResponse(BaseModel):
    id: str
    udid: str
    platform: str
    serial_number: str | None
    model: str | None
    os_version: str | None
    hostname: str | None
    status: str
    psso_status: str
    enrolled_at: datetime | None
    last_checkin: datetime | None

    model_config = {"from_attributes": True}


class LockRequest(BaseModel):
    pin: str | None = None
    message: str | None = None


class EraseRequest(BaseModel):
    pin: str = ""


async def _get_device(device_id: str, tenant: Tenant, db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.tenant_id == tenant.id))
    return result.scalars().all()


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await _get_device(device_id, tenant, db)


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _get_device(device_id, tenant, db)
    await db.execute(delete(Device).where(Device.id == device_id, Device.tenant_id == tenant.id))


@router.post("/{device_id}/lock", status_code=202)
async def lock_device(
    device_id: str,
    body: LockRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    cmd = make_device_lock_command(device.id, tenant.id, pin=body.pin, message=body.message)
    db.add(cmd)
    return {"command_uuid": cmd.command_uuid}


@router.post("/{device_id}/erase", status_code=202)
async def erase_device(
    device_id: str,
    body: EraseRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    cmd = make_erase_device_command(device.id, tenant.id, pin=body.pin)
    db.add(cmd)
    return {"command_uuid": cmd.command_uuid}


@router.post("/{device_id}/restart", status_code=202)
async def restart_device(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    cmd = make_restart_command(device.id, tenant.id)
    db.add(cmd)
    return {"command_uuid": cmd.command_uuid}


@router.post("/{device_id}/query", status_code=202)
async def query_device(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    cmd = make_device_information_command(device.id, tenant.id)
    db.add(cmd)
    return {"command_uuid": cmd.command_uuid}
