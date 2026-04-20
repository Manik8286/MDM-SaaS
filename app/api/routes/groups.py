"""
Device Groups API.

GET    /groups                          — list all groups
POST   /groups                          — create group
GET    /groups/{id}                     — group detail with member count
PATCH  /groups/{id}                     — update name/description/color
DELETE /groups/{id}                     — delete group
GET    /groups/{id}/devices             — list devices in group
POST   /groups/{id}/devices             — add device(s) to group
DELETE /groups/{id}/devices/{device_id} — remove device from group
POST   /groups/{id}/bulk                — bulk action on all devices in group
"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, DeviceGroup, DeviceGroupMember, MdmCommand, Tenant, User
from app.core.deps import get_current_tenant, get_current_user
from app.mdm.apple.commands import (
    make_device_lock_command, make_erase_device_command,
    make_restart_command, make_device_information_command,
)
from app.mdm.windows.commands import (
    make_windows_lock, make_windows_wipe,
    make_windows_restart, make_windows_query,
)
from app.services.audit import write_audit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/groups")


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


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str | None
    color: str
    member_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    color: str = "#6366f1"


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class AddDevicesRequest(BaseModel):
    device_ids: list[str]


class GroupBulkRequest(BaseModel):
    action: str  # lock | erase | restart | query


async def _get_group(group_id: str, tenant: Tenant, db: AsyncSession) -> DeviceGroup:
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id, DeviceGroup.tenant_id == tenant.id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            DeviceGroup,
            func.count(DeviceGroupMember.id).label("member_count"),
        )
        .outerjoin(DeviceGroupMember, DeviceGroupMember.group_id == DeviceGroup.id)
        .where(DeviceGroup.tenant_id == tenant.id)
        .group_by(DeviceGroup.id)
        .order_by(DeviceGroup.created_at)
    )
    rows = result.all()
    return [
        GroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            color=g.color,
            member_count=cnt,
            created_at=g.created_at,
        )
        for g, cnt in rows
    ]


@router.post("", status_code=201)
async def create_group(
    body: CreateGroupRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = DeviceGroup(
        tenant_id=tenant.id,
        name=body.name,
        description=body.description,
        color=body.color,
    )
    db.add(group)
    await db.flush()
    await write_audit(
        db, tenant.id, "group.create", "device_group",
        actor_id=user.id, resource_id=group.id,
        changes={"name": body.name},
        ip_address=request.client.host if request.client else None,
    )
    return {"id": group.id, "name": group.name, "description": group.description, "color": group.color, "member_count": 0, "created_at": group.created_at}


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            DeviceGroup,
            func.count(DeviceGroupMember.id).label("member_count"),
        )
        .outerjoin(DeviceGroupMember, DeviceGroupMember.group_id == DeviceGroup.id)
        .where(DeviceGroup.id == group_id, DeviceGroup.tenant_id == tenant.id)
        .group_by(DeviceGroup.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    g, cnt = row
    return GroupResponse(id=g.id, name=g.name, description=g.description, color=g.color, member_count=cnt, created_at=g.created_at)


@router.patch("/{group_id}")
async def update_group(
    group_id: str,
    body: UpdateGroupRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = await _get_group(group_id, tenant, db)
    if body.name is not None:
        group.name = body.name
    if body.description is not None:
        group.description = body.description
    if body.color is not None:
        group.color = body.color
    await write_audit(
        db, tenant.id, "group.update", "device_group",
        actor_id=user.id, resource_id=group_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"id": group.id, "name": group.name, "description": group.description, "color": group.color}


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = await _get_group(group_id, tenant, db)
    await write_audit(
        db, tenant.id, "group.delete", "device_group",
        actor_id=user.id, resource_id=group_id,
        changes={"name": group.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.execute(delete(DeviceGroup).where(DeviceGroup.id == group_id, DeviceGroup.tenant_id == tenant.id))


@router.get("/{group_id}/devices")
async def list_group_devices(
    group_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _get_group(group_id, tenant, db)
    result = await db.execute(
        select(Device)
        .join(DeviceGroupMember, DeviceGroupMember.device_id == Device.id)
        .where(DeviceGroupMember.group_id == group_id, DeviceGroupMember.tenant_id == tenant.id)
        .order_by(Device.hostname)
    )
    devices = result.scalars().all()
    return [
        {
            "id": d.id, "hostname": d.hostname, "serial_number": d.serial_number,
            "platform": d.platform, "os_version": d.os_version, "status": d.status,
            "compliance_status": d.compliance_status, "last_checkin": d.last_checkin,
        }
        for d in devices
    ]


@router.post("/{group_id}/devices", status_code=201)
async def add_devices_to_group(
    group_id: str,
    body: AddDevicesRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_group(group_id, tenant, db)

    # Verify devices belong to this tenant
    devices_result = await db.execute(
        select(Device).where(Device.id.in_(body.device_ids), Device.tenant_id == tenant.id)
    )
    valid_devices = {d.id for d in devices_result.scalars().all()}

    # Avoid duplicates — fetch existing memberships
    existing_result = await db.execute(
        select(DeviceGroupMember.device_id).where(
            DeviceGroupMember.group_id == group_id,
            DeviceGroupMember.device_id.in_(body.device_ids),
        )
    )
    already_in = {row[0] for row in existing_result.all()}

    added = []
    for device_id in body.device_ids:
        if device_id in valid_devices and device_id not in already_in:
            db.add(DeviceGroupMember(group_id=group_id, device_id=device_id, tenant_id=tenant.id))
            added.append(device_id)

    await write_audit(
        db, tenant.id, "group.add_devices", "device_group",
        actor_id=user.id, resource_id=group_id,
        changes={"added": len(added)},
        ip_address=request.client.host if request.client else None,
    )
    return {"added": len(added)}


@router.delete("/{group_id}/devices/{device_id}", status_code=204)
async def remove_device_from_group(
    group_id: str,
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _get_group(group_id, tenant, db)
    await db.execute(
        delete(DeviceGroupMember).where(
            DeviceGroupMember.group_id == group_id,
            DeviceGroupMember.device_id == device_id,
            DeviceGroupMember.tenant_id == tenant.id,
        )
    )


@router.post("/{group_id}/bulk", status_code=202)
async def bulk_action_group(
    group_id: str,
    body: GroupBulkRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("lock", "erase", "restart", "query"):
        raise HTTPException(status_code=400, detail="Invalid action")

    await _get_group(group_id, tenant, db)

    result = await db.execute(
        select(Device)
        .join(DeviceGroupMember, DeviceGroupMember.device_id == Device.id)
        .where(DeviceGroupMember.group_id == group_id, DeviceGroupMember.tenant_id == tenant.id)
    )
    devices = result.scalars().all()
    if not devices:
        return {"action": body.action, "queued": 0, "command_uuids": []}

    command_uuids = []
    for device in devices:
        if body.action == "lock":
            cmd = make_device_lock_command(device.id, tenant.id) if device.platform != "windows" else make_windows_lock(device.id, tenant.id)
        elif body.action == "erase":
            cmd = make_erase_device_command(device.id, tenant.id) if device.platform != "windows" else make_windows_wipe(device.id, tenant.id)
        elif body.action == "restart":
            cmd = make_restart_command(device.id, tenant.id) if device.platform != "windows" else make_windows_restart(device.id, tenant.id)
        else:
            cmd = make_device_information_command(device.id, tenant.id) if device.platform != "windows" else make_windows_query(device.id, tenant.id)
        db.add(cmd)
        command_uuids.append(cmd.command_uuid)

    await write_audit(
        db, tenant.id, f"group.bulk_{body.action}", "device_group",
        actor_id=user.id, resource_id=group_id,
        changes={"queued": len(command_uuids)},
        ip_address=request.client.host if request.client else None,
    )
    for device in devices:
        asyncio.create_task(_push_device(device))

    return {"action": body.action, "queued": len(command_uuids), "command_uuids": command_uuids}
