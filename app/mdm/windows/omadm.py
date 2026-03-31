"""
OMA-DM (SyncML) management server — Windows device check-in handler.

Windows devices POST SyncML to /ManagementServer/MDM.svc periodically.
Server delivers queued commands and records results.

Session flow:
  1. Device sends SyncHdr + Alert 1201 (session start) + Status for prev cmds
  2. Server acks SyncHdr, delivers queued MdmCommands as SyncML verbs
  3. Device executes and replies with Status (and Results for Get commands)
  4. Server marks commands completed/failed, stores device info from Results

References:
  OMA-DM 1.2: https://www.openmobilealliance.org/release/DM/
  MS-MDM:     https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-mdm/
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import Device, MdmCommand

from .syncml import SyncCmd, SyncMsg, build, parse
from .commands import build_syncml_cmds, make_windows_query

log = logging.getLogger(__name__)
router = APIRouter()

_ALERT_SESSION_START = "1201"
_STATUS_OK = "200"


@router.post("/ManagementServer/MDM.svc")
async def omadm_sync(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    try:
        msg = parse(body)
    except Exception as e:
        log.warning("OMA-DM parse error: %s", e)
        return Response(status_code=400)

    device_uri = msg.header.source_uri
    server_uri = str(request.url)

    device = await _resolve_device(device_uri, db)
    if device:
        await db.execute(
            update(Device).where(Device.id == device.id).values(last_checkin=datetime.utcnow())
        )

    reply: list[dict] = [_status_ok(msg.header.msg_id, "0", "SyncHdr",
                                     msg.header.target_uri, device_uri)]

    for cmd in msg.commands:
        if cmd.cmd == "Alert":
            if cmd.data == _ALERT_SESSION_START:
                log.info("OMA-DM session start from %s", device_uri)
            reply.append(_status_ok(msg.header.msg_id, cmd.cmd_id, "Alert"))

        elif cmd.cmd == "Status" and device:
            await _process_status(cmd, device, db)

        elif cmd.cmd == "Results" and device:
            await _apply_device_info(cmd, device, db)

    # Auto-queue a device info query on first session (when info is missing)
    if device and not device.os_version and not device.hostname:
        has_query = await db.execute(
            select(MdmCommand).where(
                MdmCommand.device_id == device.id,
                MdmCommand.command_type == "DeviceQuery",
            ).limit(1)
        )
        if not has_query.scalar_one_or_none():
            auto_query = make_windows_query(device.id, device.tenant_id)
            db.add(auto_query)
            await db.flush()
            log.info("Auto-queued DeviceQuery for new Windows device %s", device.udid)

    # Deliver queued commands
    if device:
        queued = await _queued_commands(device.id, db)
        for db_cmd in queued:
            reply.extend(build_syncml_cmds(db_cmd))
            await db.execute(
                update(MdmCommand).where(MdmCommand.id == db_cmd.id).values(status="delivered")
            )
            log.info("Delivered Windows command %s to %s", db_cmd.command_type, device_uri)

    xml_bytes = build(
        session_id=msg.header.session_id,
        msg_id=str(int(msg.header.msg_id) + 1),
        server_uri=server_uri,
        device_uri=device_uri,
        commands=reply,
    )
    return Response(content=xml_bytes, media_type="application/vnd.syncml.dm+xml; charset=utf-8")


def _status_ok(msg_ref: str, cmd_ref: str, ref_cmd: str,
               target_ref: str = "", source_ref: str = "") -> dict:
    d: dict = {"cmd": "Status", "msg_ref": msg_ref, "cmd_ref": cmd_ref, "ref_cmd": ref_cmd, "data": "200"}
    if target_ref:
        d["target_ref"] = target_ref
    if source_ref:
        d["source_ref"] = source_ref
    return d


async def _resolve_device(device_uri: str, db: AsyncSession) -> Device | None:
    if not device_uri:
        return None
    result = await db.execute(
        select(Device).where(Device.udid == device_uri, Device.platform == "windows").limit(1)
    )
    return result.scalar_one_or_none()


async def _queued_commands(device_id: str, db: AsyncSession) -> list[MdmCommand]:
    result = await db.execute(
        select(MdmCommand)
        .where(MdmCommand.device_id == device_id, MdmCommand.status == "queued")
        .order_by(MdmCommand.queued_at)
        .limit(5)
    )
    return list(result.scalars().all())


async def _process_status(cmd: SyncCmd, device: Device, db: AsyncSession) -> None:
    """
    Match a device Status reply back to a delivered MdmCommand.
    We embed the command_uuid in the LocURI as ?id=<uuid>, parse it here.
    """
    cmd_uuid = None
    for item in cmd.items:
        uri = item.target or item.source or ""
        if "?id=" in uri:
            cmd_uuid = uri.split("?id=")[-1]
            break

    new_status = "completed" if cmd.data == _STATUS_OK else "failed"

    if cmd_uuid:
        await db.execute(
            update(MdmCommand)
            .where(MdmCommand.command_uuid == cmd_uuid)
            .values(status=new_status, executed_at=datetime.utcnow(),
                    result={"syncml_status": cmd.data})
        )
    else:
        # Fallback: mark oldest delivered command for this device
        result = await db.execute(
            select(MdmCommand)
            .where(MdmCommand.device_id == device.id, MdmCommand.status == "delivered")
            .order_by(MdmCommand.queued_at)
            .limit(1)
        )
        db_cmd = result.scalar_one_or_none()
        if db_cmd:
            await db.execute(
                update(MdmCommand).where(MdmCommand.id == db_cmd.id)
                .values(status=new_status, executed_at=datetime.utcnow(),
                        result={"syncml_status": cmd.data})
            )
    log.info("Windows command result: status=%s uuid=%s device=%s", new_status, cmd_uuid, device.udid)


async def _apply_device_info(cmd: SyncCmd, device: Device, db: AsyncSession) -> None:
    """Parse Get Results items and update Device fields."""
    updates: dict = {}
    for item in cmd.items:
        node = (item.source or item.target or "").split("?")[0].rstrip("/")
        val = (item.data or "").strip()
        if not val:
            continue
        if node.endswith("SwV"):
            updates["os_version"] = val
        elif node.endswith("Mod"):
            updates["model"] = val
        elif node.endswith("Man") and "model" not in updates:
            updates["model"] = val
        elif node.endswith("DevTyp") and "model" not in updates:
            updates["model"] = val
        elif node.endswith("DNSComputerName"):
            updates["hostname"] = val
        elif node.endswith("SMBIOSSerialNumber"):
            updates["serial_number"] = val
    if updates:
        await db.execute(update(Device).where(Device.id == device.id).values(**updates))
        log.info("Windows device info updated %s: %s", device.udid, updates)
