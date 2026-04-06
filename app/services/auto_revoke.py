"""
Auto-revoke background worker.

Runs every 60 seconds. Finds approved admin access requests where
revoke_at has passed, queues a dseditgroup revocation ScriptJob,
and marks the request as revoked.
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.base import AsyncSessionLocal
from app.db.models import AdminAccessRequest, ScriptJob
from app.mdm.apple.commands import make_user_list_command

log = logging.getLogger(__name__)


async def _run_once():
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.utcnow()
            result = await db.execute(
                select(AdminAccessRequest)
                .options(
                    selectinload(AdminAccessRequest.device_user),
                    selectinload(AdminAccessRequest.device),
                )
                .where(
                    AdminAccessRequest.status == "approved",
                    AdminAccessRequest.revoke_at <= now,
                )
            )
            expired = result.scalars().all()
            if not expired:
                return

            log.info("Auto-revoke: %d expired grants found", len(expired))
            for req in expired:
                username = req.device_user.short_name if req.device_user else None
                if not username:
                    log.warning("Auto-revoke: no username for request %s, skipping", req.id)
                    continue

                req.status = "revoked"
                req.revoked_at = now

                revocation_job = ScriptJob(
                    tenant_id=req.tenant_id,
                    device_id=req.device_id,
                    command=f"dseditgroup -o edit -d '{username}' -t user admin",
                    label="admin_revocation_auto",
                    status="pending",
                )
                db.add(revocation_job)

                cmd = make_user_list_command(req.device_id, req.tenant_id)
                db.add(cmd)

                log.info(
                    "Auto-revoke: queued revocation for user=%s device=%s request=%s",
                    username, req.device_id, req.id,
                )

                from app.services.notifications import notify
                asyncio.create_task(notify("admin_access_auto_revoked", {
                    "username": username,
                    "hostname": req.device.hostname if req.device else None,
                    "duration_hours": req.duration_hours,
                }))

            await db.commit()
        except Exception:
            log.exception("Auto-revoke worker error")
            await db.rollback()


async def auto_revoke_loop():
    log.info("Auto-revoke worker started (interval=60s)")
    while True:
        await asyncio.sleep(60)
        await _run_once()
