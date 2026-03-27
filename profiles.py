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
import plistlib
import uuid
from dataclasses import dataclass
from app.db.models import Tenant


MICROSOFT_SSO_EXTENSION_ID = "com.microsoft.CompanyPortalMac.ssoextension"
MICROSOFT_TEAM_ID = "UBF8T346G9"

ENTRA_SSO_URLS = [
    "https://login.microsoftonline.com",
    "https://login.microsoft.com",
    "https://sts.windows.net",
    "https://graph.microsoft.com",
    "https://management.azure.com",
]


@dataclass
class PssoProfileOptions:
    auth_method: str = "UserSecureEnclaveKey"  # or "Password"
    enable_create_user_at_login: bool = True
    registration_token: str = ""
    admin_groups: list[str] | None = None


def build_psso_payload(tenant: Tenant, options: PssoProfileOptions) -> dict:
    """
    Build the com.apple.extensiblesso payload dict for Entra PSSO.
    This is the core of PSSO — pushed to device via InstallProfile command.
    """
    platform_sso: dict = {
        "AuthenticationMethod": options.auth_method,
        "EnableCreateUserAtLogin": options.enable_create_user_at_login,
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
        "Urls": ENTRA_SSO_URLS,
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
) -> bytes:
    """
    Wrap one or more payload dicts into a complete .mobileconfig XML plist.
    Returns unsigned XML bytes — sign with sign_profile() before delivering to device.
    """
    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.profile.{uuid.uuid4()}",
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
    identity_cert_uuid: str,
    sign_message: bool = True,
) -> bytes:
    """
    Build the MDM enrollment payload — the initial profile that enrolls a device.
    Delivered via the enrollment token URL, not via MDM protocol.
    """
    mdm_payload = {
        "PayloadType": "com.apple.mdm",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"com.mdmsaas.mdm.{tenant.id}",
        "PayloadUUID": str(uuid.uuid4()),
        "PayloadDisplayName": "MDM Enrollment",
        "ServerURL": server_url,
        "CheckInURL": checkin_url,
        "Topic": push_topic,
        "IdentityCertificateUUID": identity_cert_uuid,
        "SignMessage": sign_message,
        "CheckOutWhenRemoved": True,
        "AccessRights": 8191,  # All rights
    }
    return build_profile_xml(
        tenant=tenant,
        payload_dicts=[mdm_payload],
        display_name=f"{tenant.name} MDM Enrollment",
        description="Enrolls this Mac in your organisation's MDM system",
    )
