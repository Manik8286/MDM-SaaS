"""
Simple CA for issuing Windows MDM device identity certificates.

For dev: auto-generates a self-signed CA at certs/dev/windows_ca.{pem,key}.
In production: replace with an actual enterprise PKI or AWS Private CA.
"""
import datetime
import logging
import os

log = logging.getLogger(__name__)

_CA_CERT_PATH = "./certs/dev/windows_ca.pem"
_CA_KEY_PATH = "./certs/dev/windows_ca.key"


def _ensure_dev_ca():
    """Return (ca_cert, ca_key), generating them if they don't exist."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if os.path.exists(_CA_CERT_PATH) and os.path.exists(_CA_KEY_PATH):
        with open(_CA_CERT_PATH, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        with open(_CA_KEY_PATH, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        return ca_cert, ca_key

    log.info("Generating Windows MDM dev CA at %s", _CA_CERT_PATH)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "MDM SaaS Dev CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MDM SaaS"),
    ])
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    os.makedirs("./certs/dev", exist_ok=True)
    with open(_CA_CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(_CA_KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    log.info("Windows MDM dev CA generated")
    return cert, key


def _parse_der_tlv(data: bytes, offset: int = 0):
    """Parse a single DER TLV. Returns (tag, raw_tlv, value, next_offset)."""
    start = offset
    tag = data[offset]; offset += 1
    lb = data[offset]; offset += 1
    if lb & 0x80:
        n = lb & 0x7F
        length = int.from_bytes(data[offset:offset + n], "big")
        offset += n
    else:
        length = lb
    value = data[offset:offset + length]
    return tag, data[start:offset + length], value, offset + length


def _extract_public_key_from_csr_der(csr_der: bytes):
    """
    Extract the public key from a PKCS#10 DER CSR without parsing the Subject.
    Used as fallback when the strict ASN.1 parser rejects non-standard PrintableString.
    Structure: SEQUENCE { SEQUENCE { INTEGER, SEQUENCE(subject), SEQUENCE(spki), ... }, ... }
    """
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    _, _, csr_content, _ = _parse_der_tlv(csr_der, 0)       # outer CertificationRequest
    _, _, cri_content, _ = _parse_der_tlv(csr_content, 0)   # CertificationRequestInfo
    off = 0
    _, _, _, off = _parse_der_tlv(cri_content, off)          # skip version INTEGER
    _, _, _, off = _parse_der_tlv(cri_content, off)          # skip Subject SEQUENCE
    _, spki_raw, _, _ = _parse_der_tlv(cri_content, off)     # SubjectPublicKeyInfo
    return load_der_public_key(spki_raw)


def cert_thumbprint(cert_der: bytes) -> str:
    """Return uppercase hex SHA1 thumbprint of a DER certificate."""
    import hashlib
    return hashlib.sha1(cert_der).hexdigest().upper()


def sign_device_csr(csr_der: bytes, device_id: str) -> tuple[bytes, bytes]:
    """
    Sign a PKCS#10 CSR (DER) with the dev CA.
    Returns (signed_cert_der, ca_cert_der).
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization

    ca_cert, ca_key = _ensure_dev_ca()
    try:
        csr = x509.load_der_x509_csr(csr_der)
        public_key = csr.public_key()
    except (ValueError, Exception) as e:
        # Windows CSRs may encode Subject with non-standard PrintableString chars.
        # We don't use the Subject anyway — extract just the public key.
        log.info("CSR strict parse failed (%s), falling back to SPKI extraction", e)
        public_key = _extract_public_key_from_csr_der(csr_der)
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "MDMSaaSDevice"),
        ]))
        .issuer_name(ca_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.DER),
        ca_cert.public_bytes(serialization.Encoding.DER),
    )
