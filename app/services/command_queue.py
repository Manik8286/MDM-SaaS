"""
SQS consumer — picks up MDM command jobs and sends APNs wake-up pushes.

Flow:
1. Command queued in mdm_commands table (status=queued)
2. SQS message: {device_id, command_id}
3. This worker: fetch device push token → send APNs push
4. Device wakes, calls /mdm/apple/connect → server returns queued command plist
"""
import json
import logging
import asyncio
import boto3
from sqlalchemy import select
from app.db.base import AsyncSessionLocal
from app.db.models import Device
from app.mdm.apple.apns import send_mdm_push, DeviceUnregisteredError
from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


async def process_message(message: dict) -> None:
    body = json.loads(message["Body"])
    device_id = body.get("device_id")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            log.warning("Device %s not found for APNs push", device_id)
            return
        if not device.push_token or not device.push_magic or not device.push_topic:
            log.warning("Device %s missing push token/magic/topic — skipping", device_id)
            return
        try:
            await send_mdm_push(
                push_token_hex=device.push_token,
                push_magic=device.push_magic,
                push_topic=device.push_topic,
            )
        except DeviceUnregisteredError:
            log.warning("Device %s token unregistered — clearing push token", device_id)
            from sqlalchemy import update
            await db.execute(
                update(Device).where(Device.id == device_id).values(push_token=None, status="token_expired")
            )
            await db.commit()


def run_consumer() -> None:
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    queue_url = settings.sqs_command_queue_url
    log.info("SQS consumer starting on queue: %s", queue_url)

    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
        )
        messages = resp.get("Messages", [])
        for msg in messages:
            try:
                asyncio.run(process_message(msg))
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            except Exception as e:
                log.exception("Failed to process SQS message: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    run_consumer()
