"""
Admin Access Request API.

Workflow:
  1. Admin creates a request for a specific device user
  2. Another admin approves or denies
  3. On approval: MDM queues UserList to confirm elevation, dashboard shows manual command
  4. Auto-revoke: background worker polls for expired grants and queues UserList refresh

GET  /admin-access/requests                — list all requests
POST /admin-access/requests                — create request
GET  /admin-access/requests/{id}           — get one request
POST /admin-access/requests/{id}/approve   — approve (queues UserList refresh)
POST /admin-access/requests/{id}/deny      — deny
POST /admin-access/requests/{id}/revoke    — manually revoke an active grant
"""
import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import AdminAccessRequest, Device, DeviceUser, ScriptJob, Tenant, User
from app.core.deps import get_current_tenant, get_current_user
from app.mdm.apple.commands import make_user_list_command
from app.services.audit import write_audit
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin-access")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateRequestBody(BaseModel):
    device_id: str
    device_user_id: str
    reason: str | None = None
    duration_hours: int = 1


class RequestResponse(BaseModel):
    id: str
    device_id: str
    device_user_id: str
    requested_by_id: str
    approved_by_id: str | None
    status: str
    reason: str | None
    duration_hours: int
    requested_at: datetime
    decided_at: datetime | None
    revoke_at: datetime | None
    revoked_at: datetime | None
    # Joined fields
    device_hostname: str | None = None
    device_serial: str | None = None
    username: str | None = None
    is_currently_admin: bool | None = None
    # Elevation instructions (shown after approval)
    elevation_command: str | None = None

    model_config = {"from_attributes": True}


def _build_response(req: AdminAccessRequest) -> RequestResponse:
    elevation_cmd = None
    if req.status == "approved":
        username = req.device_user.short_name if req.device_user else "USERNAME"
        elevation_cmd = f"sudo dseditgroup -o edit -a {username} -t user admin"

    return RequestResponse(
        id=req.id,
        device_id=req.device_id,
        device_user_id=req.device_user_id,
        requested_by_id=req.requested_by_id,
        approved_by_id=req.approved_by_id,
        status=req.status,
        reason=req.reason,
        duration_hours=req.duration_hours,
        requested_at=req.requested_at,
        decided_at=req.decided_at,
        revoke_at=req.revoke_at,
        revoked_at=req.revoked_at,
        device_hostname=req.device.hostname if req.device else None,
        device_serial=req.device.serial_number if req.device else None,
        username=req.device_user.short_name if req.device_user else None,
        is_currently_admin=req.device_user.is_admin if req.device_user else None,
        elevation_command=elevation_cmd,
    )


async def _load_request(
    request_id: str, tenant: Tenant, db: AsyncSession
) -> AdminAccessRequest:
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(AdminAccessRequest)
        .options(
            selectinload(AdminAccessRequest.device),
            selectinload(AdminAccessRequest.device_user),
            selectinload(AdminAccessRequest.requested_by),
            selectinload(AdminAccessRequest.approved_by),
        )
        .where(AdminAccessRequest.id == request_id, AdminAccessRequest.tenant_id == tenant.id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/requests", response_model=list[RequestResponse])
async def list_requests(
    status: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    q = (
        select(AdminAccessRequest)
        .options(
            selectinload(AdminAccessRequest.device),
            selectinload(AdminAccessRequest.device_user),
            selectinload(AdminAccessRequest.requested_by),
            selectinload(AdminAccessRequest.approved_by),
        )
        .where(AdminAccessRequest.tenant_id == tenant.id)
        .order_by(AdminAccessRequest.requested_at.desc())
    )
    if status:
        q = q.where(AdminAccessRequest.status == status)
    result = await db.execute(q)
    return [_build_response(r) for r in result.scalars().all()]


@router.post("/requests", response_model=RequestResponse, status_code=201)
async def create_request(
    body: CreateRequestBody,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate device belongs to tenant
    device_result = await db.execute(
        select(Device).where(Device.id == body.device_id, Device.tenant_id == tenant.id)
    )
    if not device_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Device not found")

    # Validate device user belongs to device
    du_result = await db.execute(
        select(DeviceUser).where(
            DeviceUser.id == body.device_user_id,
            DeviceUser.device_id == body.device_id,
        )
    )
    device_user = du_result.scalar_one_or_none()
    if not device_user:
        raise HTTPException(status_code=404, detail="Device user not found")

    if device_user.is_admin:
        raise HTTPException(status_code=400, detail="User is already an admin")

    if not 1 <= body.duration_hours <= 72:
        raise HTTPException(status_code=400, detail="duration_hours must be 1–72")

    req = AdminAccessRequest(
        tenant_id=tenant.id,
        device_id=body.device_id,
        device_user_id=body.device_user_id,
        requested_by_id=user.id,
        reason=body.reason,
        duration_hours=body.duration_hours,
    )
    db.add(req)
    await db.flush()

    await write_audit(
        db, tenant.id, "admin_access.requested", "admin_access_request",
        actor_id=user.id, resource_id=req.id,
        changes={"device_id": body.device_id, "username": device_user.short_name, "duration_hours": body.duration_hours},
        ip_address=request.client.host if request.client else None,
    )

    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(AdminAccessRequest)
        .options(
            selectinload(AdminAccessRequest.device),
            selectinload(AdminAccessRequest.device_user),
            selectinload(AdminAccessRequest.requested_by),
            selectinload(AdminAccessRequest.approved_by),
        )
        .where(AdminAccessRequest.id == req.id)
    )
    return _build_response(result.scalar_one())


@router.get("/requests/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return _build_response(await _load_request(request_id, tenant, db))


@router.post("/requests/{request_id}/approve", response_model=RequestResponse)
async def approve_request(
    request_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(request_id, tenant, db)
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    now = datetime.utcnow()
    req.status = "approved"
    req.approved_by_id = user.id
    req.decided_at = now
    req.revoke_at = now + timedelta(hours=req.duration_hours)

    # Queue agent script job to elevate the user automatically
    username = req.device_user.short_name
    elevation_job = ScriptJob(
        tenant_id=tenant.id,
        device_id=req.device_id,
        command=f"dseditgroup -o edit -a '{username}' -t user admin",
        label="admin_elevation",
        status="pending",
        created_by_id=user.id,
    )
    db.add(elevation_job)

    # Queue UserList to refresh admin status after elevation
    cmd = make_user_list_command(req.device_id, tenant.id)
    db.add(cmd)

    await write_audit(
        db, tenant.id, "admin_access.approved", "admin_access_request",
        actor_id=user.id, resource_id=req.id,
        changes={
            "username": req.device_user.short_name,
            "duration_hours": req.duration_hours,
            "revoke_at": req.revoke_at.isoformat(),
        },
        ip_address=request.client.host if request.client else None,
    )

    # APNs push to wake device for UserList
    async def _push():
        device = req.device
        if device and device.push_token:
            try:
                from app.mdm.apple.apns import send_mdm_push
                await send_mdm_push(
                    push_token_hex=device.push_token,
                    push_magic=device.push_magic,
                    push_topic=device.push_topic,
                )
            except Exception as e:
                log.warning("APNs push failed: %s", e)
    asyncio.create_task(_push())

    return _build_response(req)


@router.post("/requests/{request_id}/deny", response_model=RequestResponse)
async def deny_request(
    request_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(request_id, tenant, db)
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")
    req.status = "denied"
    req.approved_by_id = user.id
    req.decided_at = datetime.utcnow()
    await write_audit(
        db, tenant.id, "admin_access.denied", "admin_access_request",
        actor_id=user.id, resource_id=req.id,
        changes={"username": req.device_user.short_name},
        ip_address=request.client.host if request.client else None,
    )
    return _build_response(req)


@router.post("/requests/{request_id}/revoke", response_model=RequestResponse)
async def revoke_request(
    request_id: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(request_id, tenant, db)
    if req.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved requests can be revoked")
    req.status = "revoked"
    req.revoked_at = datetime.utcnow()
    # Queue agent script job to remove admin privileges automatically
    username = req.device_user.short_name
    revocation_job = ScriptJob(
        tenant_id=tenant.id,
        device_id=req.device_id,
        command=f"dseditgroup -o edit -d '{username}' -t user admin",
        label="admin_revocation",
        status="pending",
        created_by_id=user.id,
    )
    db.add(revocation_job)
    # Queue UserList to confirm revocation
    cmd = make_user_list_command(req.device_id, tenant.id)
    db.add(cmd)
    await write_audit(
        db, tenant.id, "admin_access.revoked", "admin_access_request",
        actor_id=user.id, resource_id=req.id,
        changes={"username": req.device_user.short_name},
        ip_address=request.client.host if request.client else None,
    )
    return _build_response(req)
