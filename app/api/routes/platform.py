"""
Platform Admin — cross-tenant customer + billing overview for the product
owner. Every other route in this app is scoped to the caller's own tenant
(get_current_tenant); this is the one deliberate exception, gated by
require_platform_admin (see app/core/deps.py) instead.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.base import get_db
from app.db.models import Tenant, User, Device
from app.core.deps import require_platform_admin

router = APIRouter(prefix="/platform")


@router.get("/tenants")
async def list_all_tenants(
    _admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    tenants = (
        await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    ).scalars().all()

    device_counts = dict(
        (await db.execute(select(Device.tenant_id, func.count(Device.id)).group_by(Device.tenant_id))).all()
    )
    user_counts = dict(
        (await db.execute(select(User.tenant_id, func.count(User.id)).group_by(User.tenant_id))).all()
    )

    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "plan": t.plan,
            "status": t.status,
            "billing_status": t.billing_status,
            "plan_device_limit": t.plan_device_limit,
            "device_count": device_counts.get(t.id, 0),
            "user_count": user_counts.get(t.id, 0),
            "trial_ends_at": t.trial_ends_at.isoformat() if t.trial_ends_at else None,
            "stripe_customer_id": t.stripe_customer_id,
            "stripe_subscription_id": t.stripe_subscription_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tenants
    ]
