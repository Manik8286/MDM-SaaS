"""
Trial-ending reminder background worker.

Runs hourly. Finds tenants still in their 5-day Stripe trial whose card will
be charged within the next 24 hours, and emails the tenant owner a heads-up.
Each tenant is only ever reminded once per trial (tracked via
trial_reminder_sent_at) so restarts/re-runs never double-send.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models import Tenant, User
from app.services.email import send_trial_ending_email

log = logging.getLogger(__name__)

REMINDER_WINDOW_HOURS = 24
CHECK_INTERVAL_SECONDS = 3600


async def _run_once():
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.utcnow()
            window_end = now + timedelta(hours=REMINDER_WINDOW_HOURS)
            result = await db.execute(
                select(Tenant).where(
                    Tenant.billing_status == "trialing",
                    Tenant.trial_ends_at.isnot(None),
                    Tenant.trial_ends_at > now,
                    Tenant.trial_ends_at <= window_end,
                    Tenant.trial_reminder_sent_at.is_(None),
                )
            )
            due = result.scalars().all()
            if not due:
                return

            log.info("Trial reminder: %d tenant(s) due", len(due))
            for tenant in due:
                owner_result = await db.execute(
                    select(User)
                    .where(User.tenant_id == tenant.id, User.role == "owner")
                    .limit(1)
                )
                owner = owner_result.scalar_one_or_none()
                if not owner:
                    log.warning("Trial reminder: no owner user for tenant=%s, skipping", tenant.id)
                    continue

                days_left = max(1, round((tenant.trial_ends_at - now).total_seconds() / 86400))
                await send_trial_ending_email(owner.email, tenant.name, days_left)
                tenant.trial_reminder_sent_at = now
                log.info("Trial reminder sent tenant=%s owner=%s days_left=%d", tenant.id, owner.email, days_left)

            await db.commit()
        except Exception:
            log.exception("Trial reminder worker error")
            await db.rollback()


async def trial_reminder_loop():
    log.info("Trial reminder worker started (interval=%ds)", CHECK_INTERVAL_SECONDS)
    while True:
        await _run_once()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
