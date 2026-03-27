"""
Unit tests for .mobileconfig profile builder.
Validates PSSO payload structure — critical for Entra ID login to work.
"""
import plistlib
import pytest
from unittest.mock import MagicMock
from app.mdm.apple.profiles import (
    build_psso_payload,
    build_psso_profile,
    build_profile_xml,
    PssoProfileOptions,
    MICROSOFT_SSO_EXTENSION_ID,
    MICROSOFT_TEAM_ID,
    ENTRA_SSO_URLS,
)


def make_mock_tenant(
    tenant_id="tenant-123",
    name="Acme Corp",
    entra_tenant_id="entra-tenant-abc",
    entra_client_id="client-id-xyz",
):
    t = MagicMock()
    t.id = tenant_id
    t.name = name
    t.entra_tenant_id = entra_tenant_id
    t.entra_client_id = entra_client_id
    return t


class TestPssoPaload:
    def test_extension_identifier(self):
        tenant = make_mock_tenant()
        payload = build_psso_payload(tenant, PssoProfileOptions())
        assert payload["ExtensionIdentifier"] == MICROSOFT_SSO_EXTENSION_ID

    def test_team_identifier(self):
        tenant = make_mock_tenant()
        payload = build_psso_payload(tenant, PssoProfileOptions())
        assert payload["TeamIdentifier"] == MICROSOFT_TEAM_ID

    def test_payload_type(self):
        tenant = make_mock_tenant()
        payload = build_psso_payload(tenant, PssoProfileOptions())
        assert payload["PayloadType"] == "com.apple.extensiblesso"

    def test_entra_urls_present(self):
        tenant = make_mock_tenant()
        payload = build_psso_payload(tenant, PssoProfileOptions())
        for url in ENTRA_SSO_URLS:
            assert url in payload["Urls"]

    def test_secure_enclave_auth_method(self):
        tenant = make_mock_tenant()
        options = PssoProfileOptions(auth_method="UserSecureEnclaveKey")
        payload = build_psso_payload(tenant, options)
        assert payload["PlatformSSO"]["AuthenticationMethod"] == "UserSecureEnclaveKey"

    def test_password_auth_method(self):
        tenant = make_mock_tenant()
        options = PssoProfileOptions(auth_method="Password")
        payload = build_psso_payload(tenant, options)
        assert payload["PlatformSSO"]["AuthenticationMethod"] == "Password"

    def test_enable_create_user_at_login(self):
        tenant = make_mock_tenant()
        options = PssoProfileOptions(enable_create_user_at_login=True)
        payload = build_psso_payload(tenant, options)
        assert payload["PlatformSSO"]["EnableCreateUserAtLogin"] is True

    def test_registration_token_included(self):
        tenant = make_mock_tenant()
        options = PssoProfileOptions(registration_token="reg-token-abc")
        payload = build_psso_payload(tenant, options)
        assert payload["PlatformSSO"]["RegistrationToken"] == "reg-token-abc"

    def test_registration_token_omitted_when_empty(self):
        tenant = make_mock_tenant()
        options = PssoProfileOptions(registration_token="")
        payload = build_psso_payload(tenant, options)
        assert "RegistrationToken" not in payload["PlatformSSO"]

    def test_admin_groups_included(self):
        tenant = make_mock_tenant()
        options = PssoProfileOptions(admin_groups=["IT-Admins", "DevOps"])
        payload = build_psso_payload(tenant, options)
        assert payload["PlatformSSO"]["AdministratorGroups"] == ["IT-Admins", "DevOps"]

    def test_payload_identifier_includes_tenant_id(self):
        tenant = make_mock_tenant(tenant_id="tenant-abc")
        payload = build_psso_payload(tenant, PssoProfileOptions())
        assert "tenant-abc" in payload["PayloadIdentifier"]


class TestProfileXml:
    def test_build_profile_is_valid_plist(self):
        tenant = make_mock_tenant()
        xml_bytes = build_psso_profile(tenant)
        parsed = plistlib.loads(xml_bytes)
        assert isinstance(parsed, dict)

    def test_profile_type(self):
        tenant = make_mock_tenant()
        parsed = plistlib.loads(build_psso_profile(tenant))
        assert parsed["PayloadType"] == "Configuration"

    def test_payload_content_has_one_entry(self):
        tenant = make_mock_tenant()
        parsed = plistlib.loads(build_psso_profile(tenant))
        assert len(parsed["PayloadContent"]) == 1

    def test_removal_disallowed_for_psso(self):
        tenant = make_mock_tenant()
        parsed = plistlib.loads(build_psso_profile(tenant))
        assert parsed["PayloadRemovalDisallowed"] is True

    def test_profile_display_name_includes_tenant(self):
        tenant = make_mock_tenant(name="Octonomy AI")
        parsed = plistlib.loads(build_psso_profile(tenant))
        assert "Octonomy AI" in parsed["PayloadDisplayName"]

    def test_profile_uuid_is_unique(self):
        tenant = make_mock_tenant()
        p1 = plistlib.loads(build_psso_profile(tenant))
        p2 = plistlib.loads(build_psso_profile(tenant))
        assert p1["PayloadUUID"] != p2["PayloadUUID"]
