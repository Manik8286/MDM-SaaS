import asyncio
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, MdmCommand, Tenant, User, DeviceUser
from app.core.deps import get_current_tenant, get_current_user
from app.core.config import get_settings

settings = get_settings()
from app.mdm.apple.commands import (
    make_device_lock_command, make_erase_device_command,
    make_restart_command, make_device_information_command,
    make_user_list_command,
)
from app.mdm.windows.commands import (
    make_windows_lock, make_windows_wipe,
    make_windows_restart, make_windows_query,
)
from app.services.audit import write_audit

log = logging.getLogger(__name__)


async def _push_device(device: Device) -> None:
    """Best-effort APNs wake push. Logs and swallows errors so the API response is never blocked."""
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
    compliance_status: str
    enrolled_at: datetime | None
    last_checkin: datetime | None

    model_config = {"from_attributes": True}


class DeviceUserResponse(BaseModel):
    id: str
    short_name: str
    full_name: str | None
    is_admin: bool
    is_logged_in: bool
    has_secure_token: bool
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class LockRequest(BaseModel):
    pin: str | None = None
    message: str | None = None


class EraseRequest(BaseModel):
    pin: str = ""


class BulkActionRequest(BaseModel):
    action: str  # lock | erase | restart | query
    device_ids: list[str]
    pin: str | None = None
    message: str | None = None


async def _get_device(device_id: str, tenant: Tenant, db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/bulk", status_code=202)
async def bulk_action(
    body: BulkActionRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("lock", "erase", "restart", "query"):
        raise HTTPException(status_code=400, detail="Invalid action. Must be lock, erase, restart, or query")
    if not body.device_ids:
        raise HTTPException(status_code=400, detail="device_ids must not be empty")

    result = await db.execute(
        select(Device).where(
            Device.id.in_(body.device_ids),
            Device.tenant_id == tenant.id,
        )
    )
    devices = result.scalars().all()
    if not devices:
        raise HTTPException(status_code=404, detail="No matching devices found")

    command_uuids = []
    for device in devices:
        if body.action == "lock":
            cmd = make_device_lock_command(device.id, tenant.id, pin=body.pin, message=body.message) if device.platform != "windows" else make_windows_lock(device.id, tenant.id)
        elif body.action == "erase":
            cmd = make_erase_device_command(device.id, tenant.id, pin=body.pin or "") if device.platform != "windows" else make_windows_wipe(device.id, tenant.id)
        elif body.action == "restart":
            cmd = make_restart_command(device.id, tenant.id) if device.platform != "windows" else make_windows_restart(device.id, tenant.id)
        else:
            cmd = make_device_information_command(device.id, tenant.id) if device.platform != "windows" else make_windows_query(device.id, tenant.id)
        db.add(cmd)
        command_uuids.append(cmd.command_uuid)

    await write_audit(
        db, tenant.id, f"device.bulk_{body.action}", "device",
        actor_id=user.id,
        changes={"device_ids": body.device_ids, "queued": len(command_uuids)},
        ip_address=request.client.host if request.client else None,
    )
    for device in devices:
        asyncio.create_task(_push_device(device))

    return {"action": body.action, "queued": len(command_uuids), "command_uuids": command_uuids}


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
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    await write_audit(
        db, tenant.id, "device.delete", "device",
        actor_id=user.id, resource_id=device_id,
        changes={"hostname": device.hostname, "udid": device.udid},
        ip_address=request.client.host if request.client else None,
    )
    await db.execute(delete(Device).where(Device.id == device_id, Device.tenant_id == tenant.id))


@router.post("/{device_id}/lock", status_code=202)
async def lock_device(
    device_id: str,
    body: LockRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    if device.platform == "windows":
        cmd = make_windows_lock(device.id, tenant.id)
    else:
        cmd = make_device_lock_command(device.id, tenant.id, pin=body.pin, message=body.message)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "device.lock", "device",
        actor_id=user.id, resource_id=device_id,
        changes={"command_uuid": cmd.command_uuid, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"command_uuid": cmd.command_uuid}


@router.post("/{device_id}/erase", status_code=202)
async def erase_device(
    device_id: str,
    body: EraseRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    if device.platform == "windows":
        cmd = make_windows_wipe(device.id, tenant.id)
    else:
        cmd = make_erase_device_command(device.id, tenant.id, pin=body.pin)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "device.erase", "device",
        actor_id=user.id, resource_id=device_id,
        changes={"command_uuid": cmd.command_uuid, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"command_uuid": cmd.command_uuid}


@router.post("/{device_id}/restart", status_code=202)
async def restart_device(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    if device.platform == "windows":
        cmd = make_windows_restart(device.id, tenant.id)
    else:
        cmd = make_restart_command(device.id, tenant.id)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "device.restart", "device",
        actor_id=user.id, resource_id=device_id,
        changes={"command_uuid": cmd.command_uuid, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"command_uuid": cmd.command_uuid}


@router.post("/{device_id}/query", status_code=202)
async def query_device(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    if device.platform == "windows":
        cmd = make_windows_query(device.id, tenant.id)
    else:
        cmd = make_device_information_command(device.id, tenant.id)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "device.query", "device",
        actor_id=user.id, resource_id=device_id,
        changes={"command_uuid": cmd.command_uuid, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"command_uuid": cmd.command_uuid}


@router.get("/{device_id}/users", response_model=list[DeviceUserResponse])
async def list_device_users(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    result = await db.execute(
        select(DeviceUser)
        .where(DeviceUser.device_id == device.id)
        .order_by(DeviceUser.is_admin.desc(), DeviceUser.short_name)
    )
    return result.scalars().all()


@router.get("/{device_id}/agent-token")
async def get_agent_token(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return (and lazily generate) the per-device agent token."""
    device = await _get_device(device_id, tenant, db)
    if not device.agent_token:
        token = str(uuid.uuid4())
        await db.execute(
            update(Device)
            .where(Device.id == device.id)
            .values(agent_token=token)
        )
        await db.flush()
        device.agent_token = token

    public_url = settings.mdm_server_url.rstrip("/")
    return {
        "device_id": device.id,
        "agent_token": device.agent_token,
        "server_url": public_url,
        "bootstrap_url": f"{public_url}/api/v1/agent/bootstrap/{device.id}",
    }


@router.post("/{device_id}/users/refresh", status_code=202)
async def refresh_device_users(
    device_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_device(device_id, tenant, db)
    cmd = make_user_list_command(device.id, tenant.id)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "device.user_list", "device",
        actor_id=user.id, resource_id=device_id,
        changes={"command_uuid": cmd.command_uuid, "hostname": device.hostname},
        ip_address=request.client.host if request.client else None,
    )
    asyncio.create_task(_push_device(device))
    return {"command_uuid": cmd.command_uuid}
