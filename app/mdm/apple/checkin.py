"""
Apple MDM check-in endpoint handler.
PUT /mdm/apple/checkin

Handles device check-in message types:
- Authenticate: device first contacts server during enrollment
- TokenUpdate:  device provides APNs push tokens
- CheckOut:     device unenrolls

Auth: mTLS (device certificate) — no JWT.
Tenant is resolved from device UDID lookup.

Spec: https://developer.apple.com/documentation/devicemanagement/check-in
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.base import get_db
from app.db.models import Device, Tenant
from app.mdm.apple.plist import (
    decode_checkin_plist, parse_checkin_message,
    AuthenticateMessage, TokenUpdateMessage, CheckOutMessage,
    encode_empty_plist, push_token_hex,
    CheckinMessageType,
)
import logging

log = logging.getLogger(__name__)
router = APIRouter()


@router.put("/mdm/apple/checkin")
async def checkin(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty body")

    log.info("Checkin body (%d bytes) content-type: %s",
             len(body), request.headers.get("content-type"))
    try:
        data = decode_checkin_plist(body)
    except ValueError as e:
        log.warning("Checkin plist parse error: %s | raw (first 200): %s", e, body[:200])
        raise HTTPException(status_code=400, detail="Invalid plist")

    log.info("Checkin plist keys: %s", list(data.keys()))
    msg = parse_checkin_message(data)

    if isinstance(msg, AuthenticateMessage):
        await _handle_authenticate(msg, db)
    elif isinstance(msg, TokenUpdateMessage):
        await _handle_token_update(msg, db)
    elif isinstance(msg, CheckOutMessage):
        await _handle_checkout(msg, db)
    else:
        # GetBootstrapToken, DeclarativeManagement, UserAuthenticate — log and ack
        log.info("Unhandled checkin type: %s for UDID: %s",
                 data.get("MessageType"), data.get("UDID"))

    return Response(content=encode_empty_plist(), media_type="application/xml")


async def _handle_authenticate(msg: AuthenticateMessage, db: AsyncSession) -> None:
    """
    Device is presenting itself for enrollment.
    If device already exists: update metadata.
    If device is new: it gets created when the user installs the enrollment profile
    (via EnrollmentToken). If UDID not found, reject.
    """
    result = await db.execute(select(Device).where(Device.udid == msg.udid))
    device = result.scalar_one_or_none()

    if device is None:
        # New device — look up by enrollment flow later; for now log and accept
        log.info("Authenticate from unknown UDID %s topic %s", msg.udid, msg.topic)
        return

    await db.execute(
        update(Device)
        .where(Device.udid == msg.udid)
        .values(
            os_version=msg.os_version or device.os_version,
            serial_number=msg.serial_number or device.serial_number,
            model=msg.model or device.model,
            status="authenticating",
            push_topic=msg.topic,
            last_checkin=datetime.utcnow(),
        )
    )
    log.info("Authenticate OK: UDID=%s serial=%s", msg.udid, msg.serial_number)


async def _handle_token_update(msg: TokenUpdateMessage, db: AsyncSession) -> None:
    """
    Device provides APNs push tokens — critical for sending commands later.
    Store push_token (hex), push_magic, push_topic, unlock_token.
    """
    push_token_str = push_token_hex(msg.token)
    unlock_token_str = msg.unlock_token.hex() if msg.unlock_token else None

    result = await db.execute(select(Device).where(Device.udid == msg.udid))
    device = result.scalar_one_or_none()

    if device is None:
        # First TokenUpdate for a brand new device — resolve tenant from push topic
        # Topic format: com.mdmsaas.mdm.<slug>  or  tenant.apns_push_topic
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.apns_push_topic == msg.topic).limit(1)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            # Fallback: match slug embedded in topic com.mdmsaas.mdm.<slug>
            slug = msg.topic.split(".")[-1] if msg.topic else None
            if slug:
                tenant_result2 = await db.execute(
                    select(Tenant).where(Tenant.slug == slug).limit(1)
                )
                tenant = tenant_result2.scalar_one_or_none()
        if tenant is None:
            log.warning("TokenUpdate: cannot resolve tenant for topic %s, skipping", msg.topic)
            return
        now = datetime.utcnow()
        new_device = Device(
            tenant_id=tenant.id,
            udid=msg.udid,
            platform="macos",
            push_token=push_token_str,
            push_magic=msg.push_magic,
            push_topic=msg.topic,
            unlock_token=unlock_token_str,
            status="enrolled",
            enrolled_at=now,
            last_checkin=now,
        )
        db.add(new_device)
        log.info("TokenUpdate: new device created UDID=%s tenant=%s", msg.udid, tenant.slug)
        return

    await db.execute(
        update(Device)
        .where(Device.udid == msg.udid)
        .values(
            push_token=push_token_str,
            push_magic=msg.push_magic,
            push_topic=msg.topic,
            unlock_token=unlock_token_str,
            status="enrolled",
            enrolled_at=device.enrolled_at or datetime.utcnow(),
            last_checkin=datetime.utcnow(),
        )
    )
    log.info("TokenUpdate OK: UDID=%s push_topic=%s", msg.udid, msg.topic)


async def _handle_checkout(msg: CheckOutMessage, db: AsyncSession) -> None:
    """Device is unenrolling — clear push tokens, mark inactive."""
    await db.execute(
        update(Device)
        .where(Device.udid == msg.udid)
        .values(
            status="unenrolled",
            push_token=None,
            push_magic=None,
            last_checkin=datetime.utcnow(),
        )
    )
    log.info("CheckOut: UDID=%s", msg.udid)
