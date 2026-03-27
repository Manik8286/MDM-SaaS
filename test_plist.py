"""
Unit tests for Apple MDM plist parsing.
Tests all checkin message types with realistic sample bodies.
No DB, no network — pure plist logic.
"""
import plistlib
import pytest
from app.mdm.apple.plist import (
    decode_checkin_plist,
    parse_checkin_message,
    parse_connect_message,
    encode_command_plist,
    encode_empty_plist,
    push_token_hex,
    AuthenticateMessage,
    TokenUpdateMessage,
    CheckOutMessage,
    CommandStatus,
    CheckinMessageType,
)


def make_plist(data: dict) -> bytes:
    return plistlib.dumps(data)


# ── Authenticate ──────────────────────────────────────────────────────────────

def test_parse_authenticate_message():
    body = make_plist({
        "MessageType": "Authenticate",
        "UDID": "AAAA-BBBB-CCCC-DDDD",
        "Topic": "com.example.mdm",
        "OSVersion": "14.3.1",
        "BuildVersion": "23D60",
        "ProductName": "MacBookPro18,3",
        "SerialNumber": "C02XYZ123",
        "Model": "MacBookPro18,3",
    })
    data = decode_checkin_plist(body)
    msg = parse_checkin_message(data)

    assert isinstance(msg, AuthenticateMessage)
    assert msg.udid == "AAAA-BBBB-CCCC-DDDD"
    assert msg.topic == "com.example.mdm"
    assert msg.os_version == "14.3.1"
    assert msg.serial_number == "C02XYZ123"
    assert msg.message_type == CheckinMessageType.AUTHENTICATE


def test_authenticate_minimal_fields():
    """Device may omit optional fields."""
    body = make_plist({
        "MessageType": "Authenticate",
        "UDID": "TEST-UDID",
        "Topic": "com.test.mdm",
    })
    msg = parse_checkin_message(decode_checkin_plist(body))
    assert isinstance(msg, AuthenticateMessage)
    assert msg.os_version is None
    assert msg.serial_number is None


# ── TokenUpdate ───────────────────────────────────────────────────────────────

def test_parse_token_update():
    push_token_bytes = bytes.fromhex("aabbccddeeff0011223344556677889900112233445566778899aabbccddeeff")
    unlock_bytes = bytes.fromhex("deadbeef" * 8)
    body = make_plist({
        "MessageType": "TokenUpdate",
        "UDID": "AAAA-BBBB-CCCC-DDDD",
        "Topic": "com.example.mdm",
        "PushMagic": "push-magic-string-12345",
        "Token": push_token_bytes,
        "UnlockToken": unlock_bytes,
    })
    msg = parse_checkin_message(decode_checkin_plist(body))

    assert isinstance(msg, TokenUpdateMessage)
    assert msg.udid == "AAAA-BBBB-CCCC-DDDD"
    assert msg.push_magic == "push-magic-string-12345"
    assert msg.token == push_token_bytes
    assert msg.unlock_token == unlock_bytes


def test_push_token_hex_conversion():
    raw = bytes.fromhex("aabbccdd")
    assert push_token_hex(raw) == "aabbccdd"


def test_token_update_without_unlock_token():
    body = make_plist({
        "MessageType": "TokenUpdate",
        "UDID": "X",
        "Topic": "com.test.mdm",
        "PushMagic": "magic",
        "Token": b"\xaa\xbb",
    })
    msg = parse_checkin_message(decode_checkin_plist(body))
    assert isinstance(msg, TokenUpdateMessage)
    assert msg.unlock_token is None


# ── CheckOut ──────────────────────────────────────────────────────────────────

def test_parse_checkout():
    body = make_plist({
        "MessageType": "CheckOut",
        "UDID": "AAAA-BBBB-CCCC-DDDD",
        "Topic": "com.example.mdm",
    })
    msg = parse_checkin_message(decode_checkin_plist(body))
    assert isinstance(msg, CheckOutMessage)
    assert msg.udid == "AAAA-BBBB-CCCC-DDDD"


# ── Unknown message type ───────────────────────────────────────────────────────

def test_unknown_message_type_returns_raw_dict():
    body = make_plist({
        "MessageType": "GetBootstrapToken",
        "UDID": "AAAA-BBBB",
        "Topic": "com.test.mdm",
    })
    msg = parse_checkin_message(decode_checkin_plist(body))
    assert isinstance(msg, dict)
    assert msg["MessageType"] == "GetBootstrapToken"


# ── Connect / command result ───────────────────────────────────────────────────

def test_parse_idle_connect():
    body = make_plist({"UDID": "DEVICE-1", "Status": "Idle"})
    msg = parse_connect_message(decode_checkin_plist(body))
    assert msg.status == CommandStatus.IDLE
    assert msg.command_uuid is None


def test_parse_acknowledged_result():
    body = make_plist({
        "UDID": "DEVICE-1",
        "Status": "Acknowledged",
        "CommandUUID": "cmd-uuid-1234",
    })
    msg = parse_connect_message(decode_checkin_plist(body))
    assert msg.status == CommandStatus.ACKNOWLEDGED
    assert msg.command_uuid == "cmd-uuid-1234"


def test_parse_error_result_with_chain():
    body = make_plist({
        "UDID": "DEVICE-1",
        "Status": "Error",
        "CommandUUID": "cmd-uuid-5678",
        "ErrorChain": [
            {"ErrorCode": 12021, "ErrorDomain": "MCMDMErrorDomain",
             "LocalizedDescription": "Profile installation failed"},
        ],
    })
    msg = parse_connect_message(decode_checkin_plist(body))
    assert msg.status == "Error"
    assert len(msg.error_chain) == 1
    assert msg.error_chain[0]["ErrorCode"] == 12021


# ── Command encoding ───────────────────────────────────────────────────────────

def test_encode_device_lock_command():
    plist_bytes = encode_command_plist("DeviceLock", "uuid-123", {"PIN": "123456"})
    decoded = plistlib.loads(plist_bytes)
    assert decoded["CommandUUID"] == "uuid-123"
    assert decoded["Command"]["RequestType"] == "DeviceLock"
    assert decoded["Command"]["PIN"] == "123456"


def test_encode_command_without_params():
    plist_bytes = encode_command_plist("RestartDevice", "uuid-456")
    decoded = plistlib.loads(plist_bytes)
    assert decoded["Command"]["RequestType"] == "RestartDevice"


def test_encode_install_profile_command():
    fake_profile = b"<plist>fake</plist>"
    import base64
    params = {"Payload": base64.b64encode(fake_profile).decode()}
    plist_bytes = encode_command_plist("InstallProfile", "uuid-789", params)
    decoded = plistlib.loads(plist_bytes)
    assert decoded["Command"]["RequestType"] == "InstallProfile"
    assert "Payload" in decoded["Command"]


def test_encode_empty_plist():
    plist_bytes = encode_empty_plist()
    decoded = plistlib.loads(plist_bytes)
    assert decoded == {}


# ── Error handling ─────────────────────────────────────────────────────────────

def test_decode_invalid_plist_raises():
    with pytest.raises(ValueError, match="Failed to parse"):
        decode_checkin_plist(b"this is not a plist")


def test_decode_empty_body_raises():
    with pytest.raises(ValueError):
        decode_checkin_plist(b"")
