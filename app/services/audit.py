from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    tenant_id: str,
    action: str,
    resource_type: str,
    actor_id: str | None = None,
    resource_id: str | None = None,
    changes: dict | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        ip_address=ip_address,
    )
    db.add(entry)
