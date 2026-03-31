from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import AuditLog, User, Tenant
from app.core.deps import get_current_tenant

router = APIRouter(prefix="/audit")


class AuditLogResponse(BaseModel):
    id: str
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    changes: dict | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    q = select(AuditLog).where(AuditLog.tenant_id == tenant.id)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if action:
        q = q.where(AuditLog.action == action)
    q = q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    logs = result.scalars().all()

    # Bulk-fetch actor emails
    actor_ids = {l.actor_id for l in logs if l.actor_id}
    actor_map: dict[str, str] = {}
    if actor_ids:
        users_result = await db.execute(select(User).where(User.id.in_(actor_ids)))
        for u in users_result.scalars():
            actor_map[u.id] = u.email

    return [
        AuditLogResponse(
            id=l.id,
            actor_email=actor_map.get(l.actor_id) if l.actor_id else None,
            action=l.action,
            resource_type=l.resource_type,
            resource_id=l.resource_id,
            changes=l.changes,
            ip_address=l.ip_address,
            created_at=l.created_at,
        )
        for l in logs
    ]
