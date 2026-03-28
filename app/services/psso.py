from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.models import Device, Tenant
from app.mdm.apple.profiles import build_psso_profile, PssoProfileOptions
from app.mdm.apple.commands import make_install_profile_command


async def push_psso_to_all_devices(
    db: AsyncSession,
    tenant: Tenant,
    options: PssoProfileOptions | None = None,
) -> list[str]:
    """Queue PSSO InstallProfile command for every enrolled device in tenant."""
    profile_xml = build_psso_profile(tenant, options)

    result = await db.execute(
        select(Device).where(Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    devices = result.scalars().all()

    command_uuids = []
    for device in devices:
        cmd = make_install_profile_command(device.id, tenant.id, profile_xml)
        db.add(cmd)
        command_uuids.append(cmd.command_uuid)

    return command_uuids


async def update_psso_status(db: AsyncSession, device_id: str, psso_status: str) -> None:
    await db.execute(
        update(Device).where(Device.id == device_id).values(psso_status=psso_status)
    )
