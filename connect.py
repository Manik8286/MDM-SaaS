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
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.base import get_db
from app.db.models import Device, MdmCommand
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
            .values(last_checkin=datetime.now(timezone.utc))
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
            executed_at=datetime.now(timezone.utc),
        )
    )
    log.info("Command %s result: %s", result_msg.command_uuid, new_status)


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
        # Mark as sent (in-flight)
        await db.execute(
            update(MdmCommand)
            .where(MdmCommand.id == command.id)
            .values(status="sent")
        )
    return command
