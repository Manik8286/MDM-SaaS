#!/usr/bin/env python3
"""
Remove conflicting PSSO profiles from a device then re-push PSSO.
Run via ECS: scripts/remove_psso_profiles.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.db.models import Device
from app.mdm.apple.commands import make_remove_profile_command

DATABASE_URL = os.environ["DATABASE_URL"]
DEVICE_UDID = os.environ.get("TARGET_UDID", "FE80ACA1-1924-508A-BE58-42655557D5CD")
PROFILE_IDS = [
    "com.mdmsaas.profile.9508bd86-e47d-4a27-9a13-bc021a6c9a54",
]


async def run():
    engine = create_async_engine(DATABASE_URL)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        result = await db.execute(select(Device).where(Device.udid == DEVICE_UDID))
        device = result.scalar_one_or_none()
        if not device:
            print(f"Device {DEVICE_UDID} not found")
            return
        for pid in PROFILE_IDS:
            cmd = make_remove_profile_command(device.id, device.tenant_id, pid)
            db.add(cmd)
            print(f"Queued RemoveProfile for {pid} → command_uuid={cmd.command_uuid}")
        await db.commit()
        print("Done — APNs push will be sent on next check-in or manual trigger.")

asyncio.run(run())
