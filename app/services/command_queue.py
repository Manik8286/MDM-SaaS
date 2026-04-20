"""
SQS consumer — picks up MDM command jobs and sends APNs wake-up pushes.

Flow:
1. Command queued in mdm_commands table (status=queued)
2. SQS message: {device_id, command_id}
3. This worker: fetch device push token → send APNs push
4. Device wakes, calls /mdm/apple/connect → server returns queued command plist

Reliability improvements vs the original:
- Visibility timeout is extended mid-processing so the message isn't re-delivered
  if processing takes longer than the queue's default window.
- Messages that fail MAX_ATTEMPTS times are NOT deleted; SQS routes them to the
  DLQ automatically once its maxReceiveCount is exceeded.
- The event loop is created once and reused across messages (no asyncio.run per msg).
- SIGTERM / SIGINT set a shutdown flag so the loop drains cleanly.
- Structured log fields (device_id, attempt, receipt_handle suffix) aid debugging.
"""
import asyncio
import json
import logging
import os
import signal
import threading

import boto3
from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.base import AsyncSessionLocal
from app.db.models import Device
from app.mdm.apple.apns import send_mdm_push, DeviceUnregisteredError

log = logging.getLogger(__name__)
settings = get_settings()

# How long (seconds) to extend the visibility timeout while we process a message.
# Must be shorter than the SQS queue's visibility timeout so we don't extend forever.
_VISIBILITY_EXTENSION_SECS = 25
_POLL_WAIT_SECS = 20          # SQS long-poll window
_BATCH_SIZE = 10              # messages per receive call

_shutdown = threading.Event()


def _handle_signal(signum, _frame) -> None:
    log.info("Received signal %s — shutting down SQS consumer", signum)
    _shutdown.set()


async def _process_message(sqs_client, queue_url: str, message: dict) -> None:
    """
    Process one SQS message.  Extends visibility timeout mid-flight, then
    deletes the message on success.  On failure the message is NOT deleted so
    SQS can re-deliver it (up to the queue's maxReceiveCount, then → DLQ).
    """
    receipt = message["ReceiptHandle"]
    receipt_suffix = receipt[-12:]          # for log correlation without leaking the full handle
    attempt = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))

    try:
        body = json.loads(message["Body"])
    except json.JSONDecodeError:
        log.error("Invalid JSON in SQS message (receipt=...%s) — sending to DLQ", receipt_suffix)
        # Delete malformed messages immediately; they will never succeed.
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
        return

    device_id = body.get("device_id")
    log.info("Processing SQS message device_id=%s attempt=%d receipt=...%s",
             device_id, attempt, receipt_suffix)

    # Extend visibility so the message isn't re-queued while we're working
    try:
        sqs_client.change_message_visibility(
            QueueUrl=queue_url,
            ReceiptHandle=receipt,
            VisibilityTimeout=_VISIBILITY_EXTENSION_SECS,
        )
    except Exception:
        log.warning("Could not extend visibility timeout for receipt=...%s", receipt_suffix)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()

        if not device:
            log.warning("Device %s not found — deleting message", device_id)
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
            return

        if not (device.push_token and device.push_magic and device.push_topic):
            log.info("Device %s missing push credentials — command will be picked up on next poll",
                     device_id)
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
            return

        try:
            await send_mdm_push(
                push_token_hex=device.push_token,
                push_magic=device.push_magic,
                push_topic=device.push_topic,
            )
            log.info("APNs push delivered device_id=%s", device_id)
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)

        except DeviceUnregisteredError:
            log.warning("APNs 410 for device %s — clearing push token", device_id)
            await db.execute(
                update(Device)
                .where(Device.id == device_id)
                .values(push_token=None, status="token_expired")
            )
            await db.commit()
            # Token is gone; no point retrying — delete the message.
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)

        except Exception as exc:
            # Leave the message in the queue; SQS will re-deliver it.
            # After maxReceiveCount deliveries it goes to the DLQ automatically.
            log.exception(
                "APNs push failed device_id=%s attempt=%d receipt=...%s — will retry: %s",
                device_id, attempt, receipt_suffix, exc,
            )


def _consumer_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Blocking poll loop. Runs on a background thread with its own event loop."""
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    queue_url = settings.sqs_command_queue_url
    log.info("SQS consumer started queue=%s", queue_url)

    while not _shutdown.is_set():
        try:
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=_BATCH_SIZE,
                WaitTimeSeconds=_POLL_WAIT_SECS,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception:
            log.exception("SQS receive_message failed — backing off 5 s")
            _shutdown.wait(timeout=5)
            continue

        messages = resp.get("Messages", [])
        if not messages:
            continue

        futures = [
            asyncio.run_coroutine_threadsafe(
                _process_message(sqs, queue_url, msg), loop
            )
            for msg in messages
        ]
        for fut in futures:
            try:
                fut.result(timeout=60)
            except Exception:
                log.exception("Unexpected error in message future")

    log.info("SQS consumer shutdown complete")


def run_consumer() -> None:
    """
    Entry point.  Sets up signal handlers, creates a single asyncio event loop
    that lives for the lifetime of the process, then starts the poll loop.
    """
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the async event loop on a dedicated thread so the blocking SQS poll
    # can co-exist with async DB + HTTP calls.
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    try:
        _consumer_loop(loop)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=10)
        loop.close()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    run_consumer()
