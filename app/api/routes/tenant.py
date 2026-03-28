from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Tenant, User
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
