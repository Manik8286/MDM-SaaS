"""
Apple .mobileconfig profile builder.

Builds signed XML configuration profiles for:
- PSSO (Platform Single Sign-On) with Microsoft Entra ID
- Generic MDM enrollment profiles

Spec for Extensible SSO payload:
https://developer.apple.com/documentation/devicemanagement/extensiblesingleapp
PSSO Microsoft guide:
https://learn.microsoft.com/en-us/entra/identity/devices/macos-psso-integration-guide
"""
import datetime
import os
import plistlib
import uuid
from dataclasses import dataclass
from app.db.models import Tenant


def sign_profile(
    profile_bytes: bytes,
    cert_path: str,
    key_path: str,
    ca_cert_path: str | None = None,
) -> bytes:
    """
    Sign a .mobileconfig profile using CMS (PKCS#7 SignedData).
    Returns DER-encoded signed profile bytes.
    macOS verifies this signature during profile installation.
    Embedding the CA cert in the CMS bag lets macOS build the trust chain
    even before it looks up the CA in the system trust store.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    with open(cert_path, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    with open(key_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)

    builder = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(profile_bytes)
        .add_signer(cert, key, hashes.SHA256())
    )

    if ca_cert_path and os.path.exists(ca_cert_path):
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        builder = builder.add_certificate(ca_cert)

    return builder.sign(serialization.Encoding.DER, [])

# Fixed UUID used for the device identity certificate payload inside enrollment profiles.
# Must be stable so the MDM payload's IdentityCertificateUUID always matches.
_DEVICE_IDENTITY_UUID = "3F3D1D3C-5A5B-4A4A-8A8A-1C1C1C1C1C1C"


_P12_PASSWORD = "mdmdev"
_P12_FILE = os.environ.get("DEVICE_IDENTITY_P12_PATH", "./certs/dev/device_identity.p12")


def _load_device_identity_p12() -> bytes:
    """
    Load the pre-generated OpenSSL PKCS#12 device identity certificate.
    Generated once by OpenSSL for maximum macOS keychain compatibility.
    """
    with open(_P12_FILE, "rb") as f:
        return f.read()


MICROSOFT_SSO_EXTENSION_ID = "com.microsoft.CompanyPortalMac.ssoextension"
MICROSOFT_TEAM_ID = "UBF8T346G9"

ENTRA_SSO_URLS = [
    "https://login.microsoftonline.com",
    "https://login.microsoft.com",
    "https://sts.windows.net",
    "https://graph.microsoft.com",
    "https://management.azure.com",
]

ENTRA_SSO_HOSTS = [
    "login.microsoftonline.com",
    "login.microsoft.com",
    "sts.windows.net",
    "graph.microsoft.com",
    "management.azure.com",
]


@dataclass
class PssoProfileOptions:
    auth_method: str = "UserSecureEnclaveKey"  # or "Password"
    enable_create_user_at_login: bool = True
    registration_token: str = ""
    admin_groups: list[str] | None = None


def build_usb_block_payload(tenant_id: str) -> dict:
    """
    Block external USB/Thunderbolt storage via com.apple.systemuiserver mount-controls.
    Note: full enforcement requires supervised device on macOS 13+.
    On unsupervised devices macOS may show a user-dismissable dialog.
    """
    return {
        "PayloadType": "com.apple.systemuiserver",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.usb.block.{tenant_id}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "USB Storage Block",
        "PayloadDescription": "Prevents mounting of external USB storage devices",
        "mount-controls": {
            "harddisk-external": ["deny", "eject"],
            "disk-image": ["deny"],
            "dvd": ["deny", "eject"],
            "bd": ["deny", "eject"],
            "cd": ["deny", "eject"],
        },
    }


def usb_block_profile_identifier(tenant_id: str) -> str:
    return f"com.mdmsaas.usb.block.profile.{tenant_id}"


def build_usb_block_profile(tenant: "Tenant") -> bytes:
    # Send both payloads — mount-controls for macOS 12-13, DenyExternalStorage for macOS 14+
    payload_legacy = build_usb_block_payload(tenant.id)
    payload_modern = {
        "PayloadType": "com.apple.security.diskaccess",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.usb.diskaccess.{tenant.id}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "USB Disk Access Block",
        "PayloadDescription": "Blocks access to external USB storage devices",
        "DenyExternalStorage": True,
    }
    return build_profile_xml(
        tenant=tenant,
        payload_dicts=[payload_legacy, payload_modern],
        display_name=f"{tenant.name} — USB Storage Block",
        description="Blocks mounting of external USB storage devices",
        removal_disallowed=True,
        identifier=usb_block_profile_identifier(tenant.id),
    )


def build_gatekeeper_payload(tenant_id: str, allow_identified_developers: bool = True) -> dict:
    """
    Enforce Gatekeeper via com.apple.systempolicy.control.
    allow_identified_developers=True  → allow App Store + signed apps (recommended)
    allow_identified_developers=False → App Store only (blocks most vendor apps)
    """
    return {
        "PayloadType": "com.apple.systempolicy.control",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.gatekeeper.{tenant_id}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "Gatekeeper Policy",
        "PayloadDescription": "Enforces Gatekeeper to block unidentified software",
        "EnableAssessment": True,
        "AllowIdentifiedDevelopers": allow_identified_developers,
    }


def build_gatekeeper_profile(tenant: "Tenant", allow_identified_developers: bool = True) -> bytes:
    payload = build_gatekeeper_payload(tenant.id, allow_identified_developers)
    label = "App Store + Signed Apps" if allow_identified_developers else "App Store Only"
    return build_profile_xml(
        tenant=tenant,
        payload_dicts=[payload],
        display_name=f"{tenant.name} — Gatekeeper ({label})",
        description=f"Enforces Gatekeeper policy: {label}",
        removal_disallowed=True,
    )


def build_psso_payload(tenant: Tenant, options: PssoProfileOptions) -> dict:
    """
    Build the com.apple.extensiblesso payload dict for Entra PSSO.
    This is the core of PSSO — pushed to device via InstallProfile command.
    """
    platform_sso: dict = {
        "AuthenticationMethod": options.auth_method,
        "TokenToUserMapping": {
            "AccountName": "preferred_username",
            "FullName": "name",
        },
    }
    if options.registration_token:
        platform_sso["RegistrationToken"] = options.registration_token
    if options.admin_groups:
        platform_sso["AdministratorGroups"] = options.admin_groups

    return {
        "PayloadType": "com.apple.extensiblesso",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.psso.{tenant.id}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "Platform Single Sign-On",
        "PayloadDescription": f"Enables SSO with {tenant.name} Microsoft Entra ID",
        "ExtensionIdentifier": MICROSOFT_SSO_EXTENSION_ID,
        "TeamIdentifier": MICROSOFT_TEAM_ID,
        "Type": "Credential",
        "Hosts": ENTRA_SSO_HOSTS,
        "URLs": ENTRA_SSO_URLS,
        "PlatformSSO": platform_sso,
        "ExtensionData": {
            "browser_sso_interaction_enabled": True,
            "disable_explicit_app_prompt": True,
            "AppPrefixAllowList": "com.microsoft.,com.apple.",
        },
    }


def build_profile_xml(
    tenant: Tenant,
    payload_dicts: list[dict],
    display_name: str = "MDM SaaS Configuration",
    description: str = "",
    scope: str = "System",
    removal_disallowed: bool = False,
    identifier: str | None = None,
) -> bytes:
    """
    Wrap one or more payload dicts into a complete .mobileconfig XML plist.
    Returns unsigned XML bytes — sign with sign_profile() before delivering to device.
    If identifier is provided it is used as the top-level PayloadIdentifier (must be
    deterministic for profiles that need RemoveProfile targeting).
    """
    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": identifier if identifier else f"com.mdmsaas.profile.{uuid.uuid4()}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": display_name,
        "PayloadDescription": description,
        "PayloadScope": scope,
        "PayloadRemovalDisallowed": removal_disallowed,
        "PayloadContent": payload_dicts,
    }
    return plistlib.dumps(profile)


def build_psso_profile(tenant: Tenant, options: PssoProfileOptions | None = None) -> bytes:
    """
    Convenience: build a complete PSSO .mobileconfig profile for a tenant.
    Returns unsigned XML bytes.
    """
    if options is None:
        options = PssoProfileOptions()
    payload = build_psso_payload(tenant, options)
    return build_profile_xml(
        tenant=tenant,
        payload_dicts=[payload],
        display_name=f"{tenant.name} — Platform SSO",
        description="Enables macOS login with Microsoft Entra ID credentials",
        removal_disallowed=True,
    )


def build_mdm_enrollment_profile(
    tenant: Tenant,
    server_url: str,
    checkin_url: str,
    push_topic: str,
    sign_message: bool = True,
) -> bytes:
    """
    Build the MDM enrollment payload — the initial profile that enrolls a device.
    Delivered via the enrollment token URL, not via MDM protocol.

    Includes a self-signed PKCS#12 certificate payload so that
    IdentityCertificateUUID references a real cert (required by macOS).
    The dev server does not enforce mTLS, so the cert content doesn't matter.
    """
    p12_data = _load_device_identity_p12()

    cert_payload = {
        "PayloadType": "com.apple.security.pkcs12",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.device.identity.{tenant.id}",
        "PayloadUUID": _DEVICE_IDENTITY_UUID,
        "PayloadDisplayName": "Device Identity Certificate",
        "PayloadContent": p12_data,
        "Password": _P12_PASSWORD,
    }

    mdm_payload = {
        "PayloadType": "com.apple.mdm",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.mdm.{tenant.id}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "MDM Enrollment",
        "ServerURL": server_url,
        "CheckInURL": checkin_url,
        "Topic": push_topic,
        "IdentityCertificateUUID": _DEVICE_IDENTITY_UUID,
        "SignMessage": sign_message,
        "CheckOutWhenRemoved": True,
        "AccessRights": 8191,  # All rights
        "ServerCapabilities": ["com.apple.mdm.per-user-connections"],
    }
    return build_profile_xml(
        tenant=tenant,
        payload_dicts=[cert_payload, mdm_payload],
        display_name=f"{tenant.name} MDM Enrollment",
        description="Enrolls this Mac in your organisation's MDM system",
    )
