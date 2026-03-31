"""
Apple MDM connect endpoint.
PUT /mdm/apple/connect

Device calls this endpoint to:
1. Report the result of the previous command
2. Receive the next queued command (or Idle if none)

The device sends a plist body containing:
- Status: Acknowledged | Error | Idle | NotNow
- CommandUUID: (if responding to a command)
- UDID: device identifier

Server responds with either:
- The next queued command as a plist
- Empty plist (Idle — no commands pending)

Spec: https://developer.apple.com/documentation/devicemanagement/implementing_device_management/sending_mdm_commands_to_a_device
"""
from datetime import datetime
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from app.db.base import get_db
from app.db.models import Device, MdmCommand, InstalledApp, DeviceUpdate, DeviceUser
from app.mdm.apple.plist import (
    decode_checkin_plist, parse_connect_message,
    encode_command_plist, encode_empty_plist,
    CommandStatus,
)
import logging

log = logging.getLogger(__name__)
router = APIRouter()


@router.put("/mdm/apple/connect")
async def connect(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    body = await request.body()

    if body:
        try:
            data = decode_checkin_plist(body)
            result_msg = parse_connect_message(data)
        except ValueError as e:
            log.warning("Connect plist parse error: %s", e)
            return Response(content=encode_empty_plist(), media_type="application/xml")

        udid = result_msg.udid

        # Update last_checkin timestamp
        await db.execute(
            update(Device)
            .where(Device.udid == udid)
            .values(last_checkin=datetime.utcnow())
        )

        # Process result of previous command if one was sent
        if result_msg.command_uuid and result_msg.status != CommandStatus.IDLE:
            await _process_command_result(result_msg, db)

        # Return next queued command for this device
        next_command = await _get_next_command(udid, db)
        if next_command:
            log.info("Delivering command %s type=%s to UDID=%s",
                     next_command.command_uuid, next_command.command_type, udid)
            return Response(
                content=encode_command_plist(
                    next_command.command_type,
                    next_command.command_uuid,
                    next_command.payload,
                ),
                media_type="application/xml",
            )

    return Response(content=encode_empty_plist(), media_type="application/xml")


async def _process_command_result(result_msg, db: AsyncSession) -> None:
    """Mark command as completed or failed based on device response."""
    new_status = (
        "completed" if result_msg.status == CommandStatus.ACKNOWLEDGED
        else "not_now" if result_msg.status == CommandStatus.NOT_NOW
        else "failed"
    )
    await db.execute(
        update(MdmCommand)
        .where(MdmCommand.command_uuid == result_msg.command_uuid)
        .values(
            status=new_status,
            result={"status": result_msg.status, "error_chain": result_msg.error_chain},
            executed_at=datetime.utcnow(),
        )
    )
    log.info("Command %s result: %s", result_msg.command_uuid, new_status)

    if result_msg.status == CommandStatus.ACKNOWLEDGED:
        qr = result_msg.raw.get("QueryResponses")
        if qr:
            await _apply_device_info(result_msg.udid, qr, db)

        app_list = result_msg.raw.get("InstalledApplicationList")
        if app_list is not None:
            await _apply_installed_apps(result_msg.udid, app_list, db)

        os_updates = result_msg.raw.get("AvailableOSUpdates")
        if os_updates is not None:
            await _apply_available_updates(result_msg.udid, os_updates, db)

        user_list = result_msg.raw.get("Users")
        if user_list is not None:
            await _apply_user_list(result_msg.udid, user_list, db)


async def _apply_device_info(udid: str, qr: dict, db: AsyncSession) -> None:
    """Write QueryResponses fields back to the Device row."""
    updates = {}
    if qr.get("SerialNumber"):
        updates["serial_number"] = qr["SerialNumber"]
    if qr.get("OSVersion"):
        updates["os_version"] = qr["OSVersion"]
    if qr.get("ModelName"):
        updates["model"] = qr["ModelName"]
    elif qr.get("Model"):
        updates["model"] = qr["Model"]
    if qr.get("DeviceName"):
        updates["hostname"] = qr["DeviceName"]
    if "IsEncrypted" in qr:
        updates["is_encrypted"] = qr["IsEncrypted"]
    if "IsSupervised" in qr:
        updates["is_supervised"] = qr["IsSupervised"]
    if not updates:
        return
    await db.execute(update(Device).where(Device.udid == udid).values(**updates))
    log.info("DeviceInformation applied for UDID=%s: %s", udid, list(updates.keys()))
    await _evaluate_compliance(udid, db)


async def _apply_installed_apps(udid: str, app_list: list, db: AsyncSession) -> None:
    """Replace installed apps snapshot for this device."""
    result = await db.execute(select(Device).where(Device.udid == udid))
    device = result.scalar_one_or_none()
    if not device:
        return
    await db.execute(delete(InstalledApp).where(InstalledApp.device_id == device.id))
    rows = [
        InstalledApp(
            device_id=device.id,
            tenant_id=device.tenant_id,
            name=app.get("Name", "Unknown"),
            bundle_id=app.get("Identifier"),
            version=app.get("Version"),
            short_version=app.get("ShortVersion"),
            source=app.get("Source"),
        )
        for app in app_list
        if app.get("Name")
    ]
    db.add_all(rows)
    log.info("InstalledApplicationList: %d apps saved for UDID=%s", len(rows), udid)
    await _evaluate_compliance(udid, db)


async def _apply_available_updates(udid: str, updates_list: list, db: AsyncSession) -> None:
    """Replace available OS updates snapshot for this device."""
    result = await db.execute(select(Device).where(Device.udid == udid))
    device = result.scalar_one_or_none()
    if not device:
        return
    await db.execute(delete(DeviceUpdate).where(DeviceUpdate.device_id == device.id))
    rows = [
        DeviceUpdate(
            device_id=device.id,
            tenant_id=device.tenant_id,
            product_key=u.get("ProductKey", ""),
            human_readable_name=u.get("HumanReadableName"),
            version=u.get("ProductVersion"),
            build=u.get("Build"),
            is_critical=bool(u.get("IsCritical", False)),
            is_config_data_only=bool(u.get("IsConfigDataOnly", False)),
            restart_required=bool(u.get("RestartRequired", False)),
            metadata_url=u.get("MetadataURL"),
        )
        for u in updates_list
        if u.get("ProductKey")
    ]
    db.add_all(rows)
    log.info("AvailableOSUpdates: %d updates saved for UDID=%s", len(rows), udid)
    await _evaluate_compliance(udid, db)


async def _evaluate_compliance(udid: str, db: AsyncSession) -> None:
    """Compute and persist compliance status based on current device state."""
    result = await db.execute(select(Device).where(Device.udid == udid))
    device = result.scalar_one_or_none()
    if not device:
        return

    issues = []

    if device.is_encrypted is False:
        issues.append("filevault_disabled")

    if not device.os_version:
        issues.append("os_version_unknown")

    if device.last_checkin:
        age_hours = (datetime.utcnow() - device.last_checkin).total_seconds() / 3600
        if age_hours > 24:
            issues.append("stale_checkin")

    critical_count_result = await db.execute(
        select(func.count()).select_from(DeviceUpdate)
        .where(DeviceUpdate.device_id == device.id, DeviceUpdate.is_critical == True)
    )
    if (critical_count_result.scalar() or 0) > 0:
        issues.append("critical_updates_pending")

    new_status = "compliant" if not issues else "non_compliant"
    await db.execute(
        update(Device).where(Device.id == device.id).values(
            compliance_status=new_status,
            compliance_checked_at=datetime.utcnow(),
        )
    )
    log.info("Compliance for UDID=%s: %s issues=%s", udid, new_status, issues)


async def _apply_user_list(udid: str, users: list, db: AsyncSession) -> None:
    """Replace local user snapshot for this device."""
    result = await db.execute(select(Device).where(Device.udid == udid))
    device = result.scalar_one_or_none()
    if not device:
        return
    await db.execute(delete(DeviceUser).where(DeviceUser.device_id == device.id))
    rows = [
        DeviceUser(
            device_id=device.id,
            tenant_id=device.tenant_id,
            user_guid=u.get("UserGUID"),
            short_name=u.get("UserShortName", ""),
            full_name=u.get("UserFullName"),
            is_admin=bool(u.get("IsAdmin", False)),
            is_logged_in=bool(u.get("IsLoggedIn", False)),
            has_secure_token=bool(u.get("HasSecureToken", False)),
        )
        for u in users
        if u.get("UserShortName")
    ]
    db.add_all(rows)
    log.info("UserList: %d users saved for UDID=%s", len(rows), udid)


async def _get_next_command(udid: str, db: AsyncSession) -> MdmCommand | None:
    """Fetch the oldest queued command for this device."""
    result = await db.execute(
        select(MdmCommand)
        .join(Device, MdmCommand.device_id == Device.id)
        .where(Device.udid == udid, MdmCommand.status == "queued")
        .order_by(MdmCommand.queued_at.asc())
        .limit(1)
    )
    command = result.scalar_one_or_none()
    if command:
        await db.execute(
            update(MdmCommand)
            .where(MdmCommand.id == command.id)
            .values(status="sent")
        )
    return command
