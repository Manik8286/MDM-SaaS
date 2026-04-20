"""
mTLS client certificate validation for Apple MDM endpoints.

In production, a reverse proxy (nginx/traefik) terminates TLS and forwards
the verified client cert as a PEM-encoded header:
  X-SSL-Client-Cert:   <URL-encoded PEM certificate>
  X-SSL-Client-Verify: SUCCESS | FAILED | NONE

In development, cert validation is skipped and a warning is logged.

Usage:
    @router.put("/mdm/apple/checkin")
    async def checkin(request: Request, cert=Depends(require_device_cert), ...):
        udid = cert["udid"]  # extracted from cert CN
"""
import logging
import urllib.parse
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import NameOID
from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Header names set by nginx ssl_client_certificate + proxy_set_header
_CERT_HEADER = "x-ssl-client-cert"
_VERIFY_HEADER = "x-ssl-client-verify"


@dataclass
class DeviceCert:
    subject_cn: str        # CN from the cert — typically the device UDID
    serial: str            # cert serial number (hex)
    fingerprint: str       # SHA-256 fingerprint (hex)
    is_validated: bool     # True = verified against CA; False = dev mode skip


def _load_ca_cert() -> x509.Certificate | None:
    """Load the MDM CA cert for chain validation. Returns None if not found."""
    try:
        with open(settings.mdm_ca_cert_path, "rb") as f:
            return x509.load_pem_x509_certificate(f.read(), default_backend())
    except FileNotFoundError:
        log.debug("CA cert not found at %s — mTLS validation will be skipped", settings.mdm_ca_cert_path)
        return None
    except Exception as e:
        log.warning("Failed to load CA cert: %s", e)
        return None


def _parse_cert_header(header_value: str) -> x509.Certificate:
    """Parse URL-encoded PEM cert from nginx proxy header."""
    pem = urllib.parse.unquote(header_value)
    if not pem.startswith("-----BEGIN"):
        # Some proxies send raw base64 without PEM armor — wrap it
        pem = f"-----BEGIN CERTIFICATE-----\n{pem}\n-----END CERTIFICATE-----\n"
    return x509.load_pem_x509_certificate(pem.encode(), default_backend())


def _validate_chain(device_cert: x509.Certificate, ca_cert: x509.Certificate) -> bool:
    """Verify device cert is signed by the CA cert (single-level chain)."""
    try:
        ca_pk = ca_cert.public_key()
        ca_pk.verify(
            device_cert.signature,
            device_cert.tbs_certificate_bytes,
            device_cert.signature_hash_algorithm,
        )
        return True
    except Exception:
        return False


async def require_device_cert(request: Request) -> DeviceCert:
    """
    FastAPI dependency that validates the mTLS client certificate.

    Development: skips validation, extracts UDID from header if present.
    Production:  requires X-SSL-Client-Verify: SUCCESS and validates chain.
    """
    is_dev = not settings.is_production

    cert_header = request.headers.get(_CERT_HEADER)
    verify_status = request.headers.get(_VERIFY_HEADER, "NONE").upper()

    # In dev without a proxy, log and return a sentinel
    if is_dev and not cert_header:
        log.warning(
            "mTLS: no client cert header on %s %s — skipping validation (dev mode)",
            request.method, request.url.path,
        )
        return DeviceCert(
            subject_cn="dev-skip",
            serial="0",
            fingerprint="dev",
            is_validated=False,
        )

    if verify_status == "FAILED":
        log.warning("mTLS: proxy rejected client cert (X-SSL-Client-Verify: FAILED) from %s", request.client)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client certificate verification failed",
        )

    if not cert_header:
        if is_dev:
            return DeviceCert(subject_cn="dev-skip", serial="0", fingerprint="dev", is_validated=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client certificate required",
        )

    try:
        cert = _parse_cert_header(cert_header)
    except Exception as e:
        log.warning("mTLS: failed to parse client cert: %s", e)
        raise HTTPException(status_code=400, detail="Malformed client certificate")

    # Check cert expiry
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    not_valid_after = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
    if now > not_valid_after:
        raise HTTPException(status_code=401, detail="Client certificate has expired")

    # Validate cert chain against CA
    ca_cert = _load_ca_cert()
    chain_valid = False
    if ca_cert:
        chain_valid = _validate_chain(cert, ca_cert)
        if not chain_valid and not is_dev:
            log.warning("mTLS: cert chain validation failed for %s", request.client)
            raise HTTPException(status_code=401, detail="Client certificate not trusted")
        elif not chain_valid:
            log.warning("mTLS: cert chain validation failed (dev mode — continuing)")
    else:
        if not is_dev:
            log.error("mTLS: CA cert not loaded — cannot validate chain in production")
            raise HTTPException(status_code=500, detail="Server mTLS configuration error")

    # Extract CN (UDID)
    try:
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except (IndexError, Exception):
        cn = "unknown"

    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    serial_hex = format(cert.serial_number, "x")

    return DeviceCert(
        subject_cn=cn,
        serial=serial_hex,
        fingerprint=fingerprint,
        is_validated=chain_valid,
    )
