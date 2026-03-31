"""
MDM command builders.
Creates MdmCommand records for the database + produces the plist payload.

All commands documented at:
https://developer.apple.com/documentation/devicemanagement/commands_and_queries
"""
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from app.db.models import MdmCommand


class CommandType(StrEnum):
    INSTALL_PROFILE = "InstallProfile"
    REMOVE_PROFILE = "RemoveProfile"
    DEVICE_INFORMATION = "DeviceInformation"
    INSTALLED_APP_LIST = "InstalledApplicationList"
    AVAILABLE_OS_UPDATES = "AvailableOSUpdates"
    SCHEDULE_OS_UPDATE_SCAN = "ScheduleOSUpdateScan"
    SCHEDULE_OS_UPDATE = "ScheduleOSUpdate"
    PROFILE_LIST = "ProfileList"
    DEVICE_LOCK = "DeviceLock"
    ERASE_DEVICE = "EraseDevice"
    RESTART_DEVICE = "RestartDevice"
    SHUTDOWN_DEVICE = "ShutDownDevice"
    INSTALLED_PROFILE_LIST = "CertificateList"
    USER_LIST = "UserList"


def make_install_profile_command(
    device_id: str,
    tenant_id: str,
    profile_xml: bytes,
) -> MdmCommand:
    """Queue an InstallProfile command. profile_xml is the signed .mobileconfig bytes."""
    import base64
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.INSTALL_PROFILE,
        status="queued",
        payload={"Payload": base64.b64encode(profile_xml).decode()},
    )


def make_device_lock_command(
    device_id: str,
    tenant_id: str,
    pin: str | None = None,
    message: str | None = None,
) -> MdmCommand:
    payload: dict = {}
    if pin:
        payload["PIN"] = pin
    if message:
        payload["Message"] = message
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.DEVICE_LOCK,
        status="queued",
        payload=payload,
    )


def make_erase_device_command(
    device_id: str,
    tenant_id: str,
    pin: str = "",
    return_to_service_config: dict | None = None,
) -> MdmCommand:
    payload: dict = {"PIN": pin}
    if return_to_service_config:
        payload["ReturnToService"] = return_to_service_config
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.ERASE_DEVICE,
        status="queued",
        payload=payload,
    )


def make_device_information_command(
    device_id: str,
    tenant_id: str,
    queries: list[str] | None = None,
) -> MdmCommand:
    default_queries = [
        "UDID", "SerialNumber", "OSVersion", "BuildVersion",
        "ModelName", "Model", "DeviceName", "WiFiMAC",
        "BluetoothMAC", "AvailableDeviceCapacity", "DeviceCapacity",
        "BatteryLevel", "IsActivationLockEnabled", "IsSupervised", "IsEncrypted",
    ]
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.DEVICE_INFORMATION,
        status="queued",
        payload={"Queries": queries or default_queries},
    )


def make_restart_command(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.RESTART_DEVICE,
        status="queued",
        payload={},
    )


def make_installed_app_list_command(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.INSTALLED_APP_LIST,
        status="queued",
        payload={},
    )


def make_available_os_updates_command(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.AVAILABLE_OS_UPDATES,
        status="queued",
        payload={},
    )


def make_schedule_os_update_scan_command(device_id: str, tenant_id: str, force: bool = False) -> MdmCommand:
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.SCHEDULE_OS_UPDATE_SCAN,
        status="queued",
        payload={"Force": force},
    )


def make_user_list_command(device_id: str, tenant_id: str) -> MdmCommand:
    """Query the list of local users on a Mac (macOS 10.13+)."""
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.USER_LIST,
        status="queued",
        payload={},
    )


def make_schedule_os_update_command(
    device_id: str,
    tenant_id: str,
    updates: list[dict],
) -> MdmCommand:
    return MdmCommand(
        id=str(uuid.uuid4()),
        device_id=device_id,
        tenant_id=tenant_id,
        command_uuid=str(uuid.uuid4()),
        command_type=CommandType.SCHEDULE_OS_UPDATE,
        status="queued",
        payload={"Updates": updates},
    )
