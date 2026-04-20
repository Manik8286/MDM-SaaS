from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select, func
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Tenant, User, Device, MdmCommand, SoftwarePackage
from app.core.deps import get_current_user, get_current_tenant

router = APIRouter(prefix="/tenant")


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    apns_push_topic: str | None
    entra_tenant_id: str | None
    entra_client_id: str | None

    model_config = {"from_attributes": True}


class TenantUpdate(BaseModel):
    name: str | None = None
    apns_cert_arn: str | None = None
    apns_key_arn: str | None = None
    apns_push_topic: str | None = None
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None


@router.get("", response_model=TenantResponse)
async def get_tenant(tenant: Tenant = Depends(get_current_tenant)):
    return tenant


@router.get("/usage")
async def get_tenant_usage(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    since_30d = datetime.utcnow() - timedelta(days=30)

    total_devices = await db.scalar(select(func.count(Device.id)).where(Device.tenant_id == tenant.id))
    enrolled = await db.scalar(select(func.count(Device.id)).where(Device.tenant_id == tenant.id, Device.status == "enrolled"))
    pending = await db.scalar(select(func.count(Device.id)).where(Device.tenant_id == tenant.id, Device.status == "pending"))
    commands_30d = await db.scalar(
        select(func.count(MdmCommand.id)).where(MdmCommand.tenant_id == tenant.id, MdmCommand.queued_at >= since_30d)
    )
    commands_queued = await db.scalar(
        select(func.count(MdmCommand.id)).where(MdmCommand.tenant_id == tenant.id, MdmCommand.status == "queued")
    )
    storage_bytes = await db.scalar(
        select(func.coalesce(func.sum(SoftwarePackage.file_size), 0)).where(SoftwarePackage.tenant_id == tenant.id)
    )

    return {
        "total_devices": total_devices or 0,
        "enrolled_devices": enrolled or 0,
        "pending_devices": pending or 0,
        "commands_last_30_days": commands_30d or 0,
        "commands_queued": commands_queued or 0,
        "storage_used_bytes": storage_bytes or 0,
        "storage_used_mb": round((storage_bytes or 0) / 1_048_576, 1),
    }


@router.patch("", response_model=TenantResponse)
async def update_tenant(
    body: TenantUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    values = body.model_dump(exclude_none=True)
    if values:
        await db.execute(update(Tenant).where(Tenant.id == tenant.id).values(**values))
        await db.refresh(tenant)
    return tenant
