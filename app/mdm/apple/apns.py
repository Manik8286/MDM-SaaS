"""
Apple Push Notification Service (APNs) HTTP/2 push sender.

APNs is used to WAKE the device — not to send MDM commands directly.
After receiving the push, the device calls /mdm/apple/connect to get commands.

APNs provider API spec:
https://developer.apple.com/documentation/usernotifications/sending_push_notifications_using_command-line_tools
MDM-specific push format: the body is {"mdm": "<PushMagic>"}

Credential loading strategy:
  - Production (apns_cert_secret_arn set): load PEM from AWS Secrets Manager.
    Credentials are cached in-process; the cache is refreshed after the cert
    expiry window (72 h) so a rotation just requires a new secret version.
  - Development: read from local file paths (apns_cert_path / apns_key_path).
"""
import httpx
import json
import logging
import ssl
import tempfile
import time
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# ── Credential cache ──────────────────────────────────────────────────────────

_CACHE_TTL_SECONDS = 72 * 3600  # re-fetch from SM once per 72 h

_cred_cache: dict[str, object] = {
    "cert_pem": None,
    "key_pem": None,
    "loaded_at": 0.0,
}


def _load_from_secrets_manager() -> tuple[str, str]:
    """Fetch APNs cert + key PEM strings from AWS Secrets Manager."""
    import boto3

    sm = boto3.client("secretsmanager", region_name=settings.aws_region)

    cert_secret = sm.get_secret_value(SecretId=settings.apns_cert_secret_arn)
    key_secret = sm.get_secret_value(SecretId=settings.apns_key_secret_arn)

    # Secrets Manager stores binary as base64 in SecretBinary or plain text in SecretString
    cert_pem = cert_secret.get("SecretString") or cert_secret["SecretBinary"].decode()
    key_pem = key_secret.get("SecretString") or key_secret["SecretBinary"].decode()

    log.info("APNs credentials loaded from Secrets Manager")
    return cert_pem, key_pem


def _get_credentials() -> tuple[str, str]:
    """Return (cert_pem, key_pem). Uses SM in prod, files in dev. Cached."""
    now = time.monotonic()
    age = now - _cred_cache["loaded_at"]  # type: ignore[operator]

    if _cred_cache["cert_pem"] and age < _CACHE_TTL_SECONDS:
        return _cred_cache["cert_pem"], _cred_cache["key_pem"]  # type: ignore[return-value]

    if settings.is_production and settings.apns_cert_secret_arn:
        cert_pem, key_pem = _load_from_secrets_manager()
    else:
        cert_path = Path(settings.apns_cert_path)
        key_path = Path(settings.apns_key_path)
        if not cert_path.exists() or not key_path.exists():
            raise FileNotFoundError(
                f"APNs cert/key not found at {cert_path} / {key_path}. "
                "Set apns_cert_path and apns_key_path or configure Secrets Manager ARNs."
            )
        cert_pem = cert_path.read_text()
        key_pem = key_path.read_text()
        log.debug("APNs credentials loaded from local files")

    _cred_cache["cert_pem"] = cert_pem
    _cred_cache["key_pem"] = key_pem
    _cred_cache["loaded_at"] = now
    return cert_pem, key_pem


def _build_ssl_context(cert_pem: str, key_pem: str) -> ssl.SSLContext:
    """Build an SSL context from in-memory PEM strings (no temp files needed)."""
    ctx = ssl.create_default_context()
    # load_cert_chain requires file paths; write to named temp files
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cf:
        cf.write(cert_pem.encode())
        cert_file = cf.name
    with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as kf:
        kf.write(key_pem.encode())
        key_file = kf.name
    try:
        ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    finally:
        Path(cert_file).unlink(missing_ok=True)
        Path(key_file).unlink(missing_ok=True)
    return ctx


# ── Exceptions ────────────────────────────────────────────────────────────────

class ApnsError(Exception):
    def __init__(self, reason: str, status_code: int):
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"APNs error {status_code}: {reason}")


class DeviceUnregisteredError(ApnsError):
    """Raised when APNs returns 410 — device token is no longer valid."""
    pass


# ── Push sender ───────────────────────────────────────────────────────────────

async def send_mdm_push(
    push_token_hex: str,
    push_magic: str,
    push_topic: str,
    cert_path: str | None = None,
    key_path: str | None = None,
) -> None:
    """
    Send a wake-up push to a managed Mac device.

    cert_path / key_path are accepted for backwards-compat with callers that
    pass explicit paths (e.g. tests). When omitted the credential loader above
    is used (Secrets Manager in prod, local files in dev).
    """
    host = settings.apns_host

    if cert_path and key_path:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    else:
        cert_pem, key_pem = _get_credentials()
        ssl_ctx = _build_ssl_context(cert_pem, key_pem)

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
