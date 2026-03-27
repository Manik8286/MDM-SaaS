"""
Unit tests for MDM command builders.
"""
import base64
import plistlib
import pytest
from app.mdm.apple.commands import (
    make_device_lock_command,
    make_erase_device_command,
    make_restart_command,
    make_device_information_command,
    make_install_profile_command,
    CommandType,
)
from app.mdm.apple.plist import encode_command_plist


DEVICE_ID = "device-uuid-1"
TENANT_ID = "tenant-uuid-1"


def test_device_lock_command_type():
    cmd = make_device_lock_command(DEVICE_ID, TENANT_ID)
    assert cmd.command_type == CommandType.DEVICE_LOCK
    assert cmd.status == "queued"
    assert cmd.device_id == DEVICE_ID
    assert cmd.tenant_id == TENANT_ID


def test_device_lock_with_pin():
    cmd = make_device_lock_command(DEVICE_ID, TENANT_ID, pin="123456")
    assert cmd.payload["PIN"] == "123456"


def test_device_lock_with_message():
    cmd = make_device_lock_command(DEVICE_ID, TENANT_ID, message="Locked by IT")
    assert cmd.payload["Message"] == "Locked by IT"


def test_erase_device_command_type():
    cmd = make_erase_device_command(DEVICE_ID, TENANT_ID)
    assert cmd.command_type == CommandType.ERASE_DEVICE
    assert cmd.status == "queued"


def test_restart_command():
    cmd = make_restart_command(DEVICE_ID, TENANT_ID)
    assert cmd.command_type == CommandType.RESTART_DEVICE
    assert cmd.payload == {}


def test_device_information_default_queries():
    cmd = make_device_information_command(DEVICE_ID, TENANT_ID)
    assert "UDID" in cmd.payload["Queries"]
    assert "SerialNumber" in cmd.payload["Queries"]
    assert "OSVersion" in cmd.payload["Queries"]


def test_device_information_custom_queries():
    cmd = make_device_information_command(DEVICE_ID, TENANT_ID, queries=["UDID", "Model"])
    assert cmd.payload["Queries"] == ["UDID", "Model"]


def test_install_profile_command():
    fake_xml = b"<plist><dict></dict></plist>"
    cmd = make_install_profile_command(DEVICE_ID, TENANT_ID, fake_xml)
    assert cmd.command_type == CommandType.INSTALL_PROFILE
    # Payload should have base64-encoded profile
    encoded = base64.b64decode(cmd.payload["Payload"])
    assert encoded == fake_xml


def test_each_command_gets_unique_uuid():
    cmd1 = make_restart_command(DEVICE_ID, TENANT_ID)
    cmd2 = make_restart_command(DEVICE_ID, TENANT_ID)
    assert cmd1.command_uuid != cmd2.command_uuid
    assert cmd1.id != cmd2.id


def test_plist_encode_device_lock():
    """Verify the plist output a device would actually receive."""
    plist_bytes = encode_command_plist("DeviceLock", "test-uuid", {"PIN": "000000"})
    decoded = plistlib.loads(plist_bytes)
    assert decoded["CommandUUID"] == "test-uuid"
    assert decoded["Command"]["RequestType"] == "DeviceLock"
    assert decoded["Command"]["PIN"] == "000000"


def test_plist_encode_install_profile():
    fake_xml = b"<plist/>"
    params = {"Payload": base64.b64encode(fake_xml).decode()}
    plist_bytes = encode_command_plist("InstallProfile", "profile-uuid", params)
    decoded = plistlib.loads(plist_bytes)
    assert decoded["Command"]["RequestType"] == "InstallProfile"
    recovered = base64.b64decode(decoded["Command"]["Payload"])
    assert recovered == fake_xml
