"""
Windows MDM command builders — OMA-DM CSP paths.

Windows MDM uses Configuration Service Providers (CSPs) accessed via SyncML.
Each action maps to a CSP node URI and a SyncML command verb.

CSP references:
- RemoteLock:  https://learn.microsoft.com/en-us/windows/client-management/mdm/remotelock-csp
- RemoteWipe:  https://learn.microsoft.com/en-us/windows/client-management/mdm/remotewipe-csp
- Reboot:      https://learn.microsoft.com/en-us/windows/client-management/mdm/reboot-csp
- DevDetail:   https://learn.microsoft.com/en-us/windows/client-management/mdm/devdetail-csp
- DevInfo:     https://learn.microsoft.com/en-us/windows/client-management/mdm/devinfo-csp
"""
from app.db.models import MdmCommand


def make_windows_lock(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        device_id=device_id,
        tenant_id=tenant_id,
        command_type="RemoteLock",
        payload={
            "command_type": "RemoteLock",
            "params": {"target": "./Vendor/MSFT/RemoteLock/Lock"},
        },
    )


def make_windows_wipe(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        device_id=device_id,
        tenant_id=tenant_id,
        command_type="RemoteWipe",
        payload={
            "command_type": "RemoteWipe",
            "params": {"target": "./Device/Vendor/MSFT/RemoteWipe/doWipe"},
        },
    )


def make_windows_restart(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        device_id=device_id,
        tenant_id=tenant_id,
        command_type="Reboot",
        payload={
            "command_type": "Reboot",
            "params": {"target": "./Device/Vendor/MSFT/Reboot/RebootNow"},
        },
    )


def make_windows_query(device_id: str, tenant_id: str) -> MdmCommand:
    return MdmCommand(
        device_id=device_id,
        tenant_id=tenant_id,
        command_type="DeviceQuery",
        payload={
            "command_type": "DeviceQuery",
            "params": {
                "nodes": [
                    "./DevInfo/DevId",
                    "./DevInfo/Man",
                    "./DevInfo/Mod",
                    "./DevDetail/SwV",
                    "./DevDetail/HwV",
                    "./DevDetail/DevTyp",
                    "./DevDetail/Ext/Microsoft/DNSComputerName",
                    "./DevDetail/Ext/Microsoft/SMBIOSSerialNumber",
                ]
            },
        },
    )


# CSP node → SyncML command verb mapping
_CMD_VERB: dict[str, str] = {
    "RemoteLock": "Exec",
    "RemoteWipe": "Exec",
    "Reboot": "Exec",
    "DeviceQuery": "Get",
}


def build_syncml_cmds(db_cmd: MdmCommand) -> list[dict]:
    """
    Convert a stored MdmCommand into SyncML command dicts for build().
    The command UUID is embedded in the LocURI so we can match Status replies.
    """
    payload = db_cmd.payload or {}
    cmd_type = payload.get("command_type", db_cmd.command_type)
    params = payload.get("params", {})
    verb = _CMD_VERB.get(cmd_type, "Exec")

    if cmd_type == "DeviceQuery":
        nodes = params.get("nodes", [])
        return [
            {"cmd": "Get", "target": f"{node}?id={db_cmd.command_uuid}"}
            for node in nodes
        ]

    return [{
        "cmd": verb,
        "target": f"{params.get('target', '')}?id={db_cmd.command_uuid}",
        "data": params.get("data"),
    }]
