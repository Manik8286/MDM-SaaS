"""
Apple Push Notification Service (APNs) HTTP/2 push sender.

APNs is used to WAKE the device — not to send MDM commands directly.
After receiving the push, the device calls /mdm/apple/connect to get commands.

APNs provider API spec:
https://developer.apple.com/documentation/usernotifications/sending_push_notifications_using_command-line_tools
MDM-specific push format: the body is {"mdm": "<PushMagic>"}
"""
import httpx
import ssl
import json
import logging
from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


class ApnsError(Exception):
    def __init__(self, reason: str, status_code: int):
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"APNs error {status_code}: {reason}")


class DeviceUnregisteredError(ApnsError):
    """Raised when APNs returns 410 — device token is no longer valid."""
    pass


async def send_mdm_push(
    push_token_hex: str,
    push_magic: str,
    push_topic: str,
    cert_path: str | None = None,
    key_path: str | None = None,
) -> None:
    """
    Send a wake-up push to a managed Mac device.

    Args:
        push_token_hex: Device APNs token as hex string (from TokenUpdate)
        push_magic:     PushMagic value (from TokenUpdate) — included in body
        push_topic:     MDM push topic (from enrollment, e.g. com.example.mdm.voip)
        cert_path:      Path to APNs certificate PEM (uses settings default if None)
        key_path:       Path to APNs private key PEM (uses settings default if None)
    """
    cert = cert_path or settings.apns_cert_path
    key = key_path or settings.apns_key_path
    host = settings.apns_host

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.load_cert_chain(certfile=cert, keyfile=key)

    url = f"https://{host}/3/device/{push_token_hex}"
    headers = {
        "apns-push-type": "mdm",
        "apns-topic": push_topic,
        "apns-priority": "10",
        "content-type": "application/json",
    }
    body = json.dumps({"mdm": push_magic}).encode()

    async with httpx.AsyncClient(http2=True, verify=ssl_ctx) as client:
        try:
            response = await client.post(url, headers=headers, content=body)
        except httpx.ConnectError as e:
            log.error("APNs connection failed: %s", e)
            raise ApnsError("connection_failed", 0) from e

    if response.status_code == 200:
        log.info("APNs push sent to token ...%s", push_token_hex[-8:])
        return

    reason = ""
    try:
        reason = response.json().get("reason", "")
    except Exception:
        pass

    if response.status_code == 410:
        log.warning("APNs 410 DeviceUnregistered for token ...%s", push_token_hex[-8:])
        raise DeviceUnregisteredError(reason, response.status_code)

    log.error("APNs error %d: %s for token ...%s",
              response.status_code, reason, push_token_hex[-8:])
    raise ApnsError(reason, response.status_code)
