"""
Apple MDM plist helpers.

All MDM messages between device and server are XML plist bodies.
This module handles encoding and decoding for all checkin and connect
message types defined in:
https://developer.apple.com/documentation/devicemanagement/check-in
"""
import plistlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CheckinMessageType(StrEnum):
    AUTHENTICATE = "Authenticate"
    TOKEN_UPDATE = "TokenUpdate"
    CHECK_OUT = "CheckOut"
    USER_AUTHENTICATE = "UserAuthenticate"
    GET_BOOTSTRAP_TOKEN = "GetBootstrapToken"
    DECLARATIVE_MANAGEMENT = "DeclarativeManagement"


class CommandStatus(StrEnum):
    ACKNOWLEDGED = "Acknowledged"
    ERROR = "Error"
    COMMAND_FORMAT_ERROR = "CommandFormatError"
    IDLE = "Idle"
    NOT_NOW = "NotNow"


@dataclass
class AuthenticateMessage:
    """Sent by device when enrollment profile is first installed."""
    udid: str
    topic: str
    message_type: str = CheckinMessageType.AUTHENTICATE
    os_version: str | None = None
    build_version: str | None = None
    product_name: str | None = None
    serial_number: str | None = None
    model: str | None = None


@dataclass
class TokenUpdateMessage:
    """Sent after Authenticate — provides APNs push tokens."""
    udid: str
    topic: str
    push_magic: str
    token: bytes  # APNs device token (binary)
    message_type: str = CheckinMessageType.TOKEN_UPDATE
    unlock_token: bytes | None = None
    user_id: str | None = None
    user_short_name: str | None = None


@dataclass
class CheckOutMessage:
    """Sent when device unenrolls."""
    udid: str
    topic: str
    message_type: str = CheckinMessageType.CHECK_OUT


@dataclass
class CommandResultMessage:
    """Sent by device in response to a command (connect endpoint)."""
    udid: str
    status: str
    command_uuid: str | None = None
    error_chain: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def decode_checkin_plist(body: bytes) -> dict[str, Any]:
    """Parse raw plist bytes from checkin request body."""
    try:
        return plistlib.loads(body)
    except Exception as e:
        raise ValueError(f"Failed to parse checkin plist: {e}") from e


def parse_checkin_message(data: dict) -> AuthenticateMessage | TokenUpdateMessage | CheckOutMessage | dict:
    """Route parsed plist dict to a typed message object."""
    msg_type = data.get("MessageType")

    if msg_type == CheckinMessageType.AUTHENTICATE:
        return AuthenticateMessage(
            udid=data["UDID"],
            topic=data["Topic"],
            message_type=msg_type,
            os_version=data.get("OSVersion"),
            build_version=data.get("BuildVersion"),
            product_name=data.get("ProductName"),
            serial_number=data.get("SerialNumber"),
            model=data.get("Model"),
        )

    if msg_type == CheckinMessageType.TOKEN_UPDATE:
        return TokenUpdateMessage(
            udid=data["UDID"],
            topic=data["Topic"],
            push_magic=data["PushMagic"],
            token=bytes(data["Token"]),
            message_type=msg_type,
            unlock_token=bytes(data["UnlockToken"]) if "UnlockToken" in data else None,
            user_id=data.get("UserID"),
            user_short_name=data.get("UserShortName"),
        )

    if msg_type == CheckinMessageType.CHECK_OUT:
        return CheckOutMessage(
            udid=data["UDID"],
            topic=data["Topic"],
            message_type=msg_type,
        )

    # Return raw dict for unhandled types (GetBootstrapToken, DeclarativeManagement, etc.)
    return data


def parse_connect_message(data: dict) -> CommandResultMessage:
    """Parse a connect body — device reporting command result or Idle."""
    return CommandResultMessage(
        udid=data.get("UDID", ""),
        status=data.get("Status", CommandStatus.IDLE),
        command_uuid=data.get("CommandUUID"),
        error_chain=data.get("ErrorChain", []),
        raw=data,
    )


def encode_command_plist(command_type: str, command_uuid: str, params: dict | None = None) -> bytes:
    """
    Build a plist command body to send to device.
    Format: { CommandUUID: ..., Command: { RequestType: ..., ...params } }
    """
    import base64
    command: dict[str, Any] = {"RequestType": command_type}
    if params:
        # InstallProfile: Payload must be <data> bytes, not a base64 string
        if command_type == "InstallProfile" and "Payload" in params:
            p = dict(params)
            p["Payload"] = base64.b64decode(p["Payload"])
            command.update(p)
        else:
            command.update(params)
    return plistlib.dumps({"CommandUUID": command_uuid, "Command": command})


def encode_empty_plist() -> bytes:
    """Return empty plist — sent as Idle response when no commands are queued."""
    return plistlib.dumps({})


def push_token_hex(token_bytes: bytes) -> str:
    """Convert APNs token bytes to hex string for storage and APNs HTTP/2 calls."""
    return token_bytes.hex()
