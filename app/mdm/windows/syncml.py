"""
OMA-DM SyncML 1.2 encoder / decoder.

All Windows MDM check-in messages use SyncML XML over HTTP POST.
Device → server: SyncHdr + Alert 1201 (session start) + Status (prev results) + Results
Server → device: SyncHdr + Status 200 (ack) + commands + Final

References:
- OMA-DM 1.2 spec: https://www.openmobilealliance.org/release/DM/
- MS-MDM protocol: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-mdm/
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_NS = "SYNCML:SYNCML1.2"
_T = f"{{{_NS}}}"


def _t(name: str) -> str:
    return f"{_T}{name}"


def _find_text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


@dataclass
class SyncHdr:
    session_id: str
    msg_id: str
    target_uri: str   # server URI
    source_uri: str   # device URI (UDID)


@dataclass
class SyncItem:
    target: str | None = None
    source: str | None = None
    data: str | None = None
    meta_type: str | None = None
    meta_format: str | None = None


@dataclass
class SyncCmd:
    cmd: str          # Alert | Status | Replace | Exec | Get | Results | Add
    cmd_id: str
    items: list[SyncItem] = field(default_factory=list)
    # Status-specific
    msg_ref: str | None = None
    cmd_ref: str | None = None
    ref_cmd: str | None = None
    target_ref: str | None = None
    source_ref: str | None = None
    data: str | None = None   # Alert code or Status code


@dataclass
class SyncMsg:
    header: SyncHdr
    commands: list[SyncCmd]


def parse(xml_bytes: bytes) -> SyncMsg:
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))

    hdr_el = root.find(_t("SyncHdr"))
    if hdr_el is None:
        raise ValueError("Missing SyncHdr")

    loc_uris = hdr_el.findall(f".//{_t('LocURI')}")
    target_uri = loc_uris[0].text.strip() if len(loc_uris) > 0 and loc_uris[0].text else ""
    source_uri = loc_uris[1].text.strip() if len(loc_uris) > 1 and loc_uris[1].text else ""

    header = SyncHdr(
        session_id=_find_text(hdr_el, _t("SessionID")) or "0",
        msg_id=_find_text(hdr_el, _t("MsgID")) or "0",
        target_uri=target_uri,
        source_uri=source_uri,
    )

    commands: list[SyncCmd] = []
    body_el = root.find(_t("SyncBody"))
    if body_el is None:
        return SyncMsg(header=header, commands=commands)

    for el in body_el:
        name = el.tag.replace(_T, "")
        if name == "Final":
            continue

        cmd_id = _find_text(el, _t("CmdID")) or "0"

        if name == "Alert":
            commands.append(SyncCmd(cmd="Alert", cmd_id=cmd_id, data=_find_text(el, _t("Data"))))

        elif name == "Status":
            commands.append(SyncCmd(
                cmd="Status",
                cmd_id=cmd_id,
                msg_ref=_find_text(el, _t("MsgRef")),
                cmd_ref=_find_text(el, _t("CmdRef")),
                ref_cmd=_find_text(el, _t("Cmd")),
                target_ref=_find_text(el, _t("TargetRef")),
                source_ref=_find_text(el, _t("SourceRef")),
                data=_find_text(el, _t("Data")),
            ))

        else:
            items = []
            for item_el in el.findall(_t("Item")):
                tgt_el = item_el.find(_t("Target"))
                src_el = item_el.find(_t("Source"))
                data_el = item_el.find(_t("Data"))
                meta_el = item_el.find(_t("Meta"))
                meta_type = meta_format = None
                if meta_el is not None:
                    mt = meta_el.find(_t("Type"))
                    mf = meta_el.find(_t("Format"))
                    meta_type = mt.text if mt is not None else None
                    meta_format = mf.text if mf is not None else None
                items.append(SyncItem(
                    target=tgt_el.findtext(_t("LocURI")) if tgt_el is not None else None,
                    source=src_el.findtext(_t("LocURI")) if src_el is not None else None,
                    data=data_el.text if data_el is not None else None,
                    meta_type=meta_type,
                    meta_format=meta_format,
                ))
            commands.append(SyncCmd(cmd=name, cmd_id=cmd_id, items=items))

    return SyncMsg(header=header, commands=commands)


def build(
    session_id: str,
    msg_id: str,
    server_uri: str,
    device_uri: str,
    commands: list[dict],
) -> bytes:
    """
    Serialize a SyncML response.
    Each command dict must have a 'cmd' key; remaining keys are cmd-specific.
    """
    root = ET.Element("SyncML", attrib={"xmlns": _NS})

    hdr = ET.SubElement(root, "SyncHdr")
    ET.SubElement(hdr, "VerDTD").text = "1.2"
    ET.SubElement(hdr, "VerProto").text = "DM/1.2"
    ET.SubElement(hdr, "SessionID").text = session_id
    ET.SubElement(hdr, "MsgID").text = msg_id
    tgt = ET.SubElement(hdr, "Target")
    ET.SubElement(tgt, "LocURI").text = device_uri
    src = ET.SubElement(hdr, "Source")
    ET.SubElement(src, "LocURI").text = server_uri

    body = ET.SubElement(root, "SyncBody")

    for idx, cmd in enumerate(commands, start=1):
        name = cmd["cmd"]
        el = ET.SubElement(body, name)
        ET.SubElement(el, "CmdID").text = str(idx)

        if name == "Status":
            ET.SubElement(el, "MsgRef").text = str(cmd.get("msg_ref", "1"))
            ET.SubElement(el, "CmdRef").text = str(cmd.get("cmd_ref", "0"))
            ET.SubElement(el, "Cmd").text = cmd.get("ref_cmd", "SyncHdr")
            if cmd.get("target_ref"):
                ET.SubElement(el, "TargetRef").text = cmd["target_ref"]
            if cmd.get("source_ref"):
                ET.SubElement(el, "SourceRef").text = cmd["source_ref"]
            ET.SubElement(el, "Data").text = str(cmd.get("data", "200"))

        elif name in ("Replace", "Add"):
            item = ET.SubElement(el, "Item")
            if cmd.get("target"):
                t = ET.SubElement(item, "Target")
                ET.SubElement(t, "LocURI").text = cmd["target"]
            if cmd.get("meta_format") or cmd.get("meta_type"):
                meta = ET.SubElement(item, "Meta")
                if cmd.get("meta_format"):
                    ET.SubElement(meta, "Format").text = cmd["meta_format"]
                if cmd.get("meta_type"):
                    ET.SubElement(meta, "Type").text = cmd["meta_type"]
            if cmd.get("data") is not None:
                ET.SubElement(item, "Data").text = str(cmd["data"])

        elif name == "Exec":
            item = ET.SubElement(el, "Item")
            t = ET.SubElement(item, "Target")
            ET.SubElement(t, "LocURI").text = cmd.get("target", "")
            if cmd.get("data") is not None:
                ET.SubElement(item, "Data").text = str(cmd["data"])

        elif name == "Get":
            item = ET.SubElement(el, "Item")
            t = ET.SubElement(item, "Target")
            ET.SubElement(t, "LocURI").text = cmd.get("target", "")

        elif name == "Alert":
            ET.SubElement(el, "Data").text = str(cmd.get("data", "1200"))

    ET.SubElement(body, "Final")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
