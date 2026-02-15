"""
XOpen v3 protocol: XML message builder and parser for BTicino thermostat.

Message format (V3):
<OWNMsg Profile="V3" Version="Official">
  <Payload>
    <Service TYPE="GET|SET|RSP" />
    <SeqID ID="0" Progress="0" Marker="0" IsLast="TRUE" />
    <Address WHO="4" WHERE="" />
    <ActionID>device_state</ActionID>
    <ParamList>
      <Params key="value" />
    </ParamList>
  </Payload>
</OWNMsg>
"""
import xml.etree.ElementTree as ET
from io import StringIO
from typing import Optional

from .models import ParsedMessage

# XOpen namespace
NS = "http://www.bticino.it/xopen/v1"
NS_MAP = {"": NS}

# WHO codes
WHO_THERMOSTAT = "4"


def _build_v3(service_type: str, action_id: str,
              params: Optional[list[dict[str, str]]] = None,
              who: str = WHO_THERMOSTAT, where: str = "",
              seq_id: str = "0", progress: str = "0") -> str:
    """Build an XOpen V3 message XML string (no XML declaration)."""
    buf = StringIO()
    buf.write(f'<OWNMsg Profile="V3" Version="Official">')
    buf.write('<Payload>')
    buf.write(f'<Service TYPE="{service_type}" />')
    buf.write(f'<SeqID ID="{seq_id}" Progress="{progress}" '
              f'Marker="0" IsLast="TRUE" />')
    buf.write(f'<Address WHO="{who}" WHERE="{where}" />')
    buf.write(f'<ActionID>{action_id}</ActionID>')
    buf.write('<ParamList>')
    if params:
        for p in params:
            attrs = ' '.join(f'{k}="{v}"' for k, v in p.items())
            buf.write(f'<Params {attrs} />')
    else:
        buf.write('<Params />')
    buf.write('</ParamList>')
    buf.write('</Payload>')
    buf.write('</OWNMsg>')
    return buf.getvalue()


# --- Handshake / negotiation messages ---

def build_negotiate_v3(sid: str = "") -> str:
    """Build OWNSetProtocol V3 negotiate message.

    Sent immediately after receiving *#*1## ACK from thermostat.
    Requests V3 protocol with command, monitor, and always-on connection.
    """
    if not sid:
        import uuid
        sid = str(uuid.uuid4())
    buf = StringIO()
    buf.write('<OWNMsg Profile="V3">')
    buf.write('<Payload>')
    buf.write('<Service TYPE="SET" />')
    buf.write(f'<SeqID ID="{sid}" Progress="0" />')
    buf.write('<Address></Address>')
    buf.write('<ActionID>OWNSetProtocol</ActionID>')
    buf.write('<ParamList>')
    buf.write('<Params Version="3" />')
    buf.write('<Params Command="1" />')
    buf.write('<Params Monitor="1" />')
    buf.write('<Params ConnAlwaysOn="1" />')
    buf.write('</ParamList>')
    buf.write('</Payload>')
    buf.write('</OWNMsg>')
    return buf.getvalue()


def build_client_handshake(sid: str, pid: int,
                           rb_decimal: str, digest: str) -> str:
    """Build ClientHandshakeHMAC message for V3 HMAC authentication.

    Note: No xmlns namespace - the C# code strips all namespace attributes.
    Note: PID should already be incremented by caller.
    """
    buf = StringIO()
    buf.write('<OWNMsg Profile="V3">')
    buf.write('<Payload>')
    buf.write('<Service TYPE="SET" />')
    buf.write(f'<SeqID ID="{sid}" Progress="{pid}" />')
    buf.write('<Address></Address>')
    buf.write('<ActionID>ClientHandshakeHMAC</ActionID>')
    buf.write('<ParamList>')
    buf.write(f'<Params Random="{rb_decimal}" />')
    buf.write(f'<Params Digest="{digest}" />')
    buf.write('</ParamList>')
    buf.write('</Payload>')
    buf.write('</OWNMsg>')
    return buf.getvalue()


def build_ack(sid: str, pid: int) -> str:
    """Build AckMsg RSP message (no xmlns, matching C# MakeMessage_V3)."""
    buf = StringIO()
    buf.write('<OWNMsg Profile="V3">')
    buf.write('<Payload>')
    buf.write('<Service TYPE="RSP" />')
    buf.write(f'<SeqID ID="{sid}" Progress="{pid}" />')
    buf.write('<Address></Address>')
    buf.write('<ActionID>AckMsg</ActionID>')
    buf.write('<ParamList />')
    buf.write('</Payload>')
    buf.write('</OWNMsg>')
    return buf.getvalue()


# --- Thermostat command messages ---

def build_get_status() -> str:
    """GET device_state - read thermostat status."""
    return _build_v3("GET", "device_state", who=WHO_THERMOSTAT)


def build_set_modality(mode: str, function: str = "HEATING",
                       setpoint: Optional[float] = None,
                       program_number: Optional[int] = None,
                       boost_minutes: Optional[int] = None,
                       temp_format: str = "CELSIUS") -> str:
    """SET device_state - change thermostat mode.

    For BOOST mode, boost_minutes (30, 60, or 90) is required.
    The timer start/end are computed automatically.
    """
    params = [
        {"temperature_format": temp_format},
        {"function": function},
        {"mode": mode},
    ]
    if setpoint is not None:
        params.append({"setpoint": str(setpoint)})
    if program_number is not None:
        params.append({"program_number": str(program_number)})

    if mode == "BOOST" and boost_minutes:
        from datetime import datetime, timedelta
        now = datetime.now()
        end = now + timedelta(minutes=boost_minutes)
        params.append({"boostTime": str(boost_minutes)})
        params.append({
            "use_date_and_time_validity": "TRUE",
            "init_date_and_time_validity": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date_and_time_validity": end.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    else:
        params.append({
            "use_date_and_time_validity": "FALSE",
            "end_date_and_time_validity": "",
            "init_date_and_time_validity": "",
        })
    return _build_v3("SET", "device_state", params, who=WHO_THERMOSTAT)


def build_keep_alive() -> str:
    """GET device_keep_alive - keepalive ping."""
    return _build_v3("GET", "device_keep_alive", who=WHO_THERMOSTAT)


def build_get_program_list() -> str:
    """GET device_program_number_list."""
    return _build_v3("GET", "device_program_number_list", who=WHO_THERMOSTAT)


# --- Response parser ---

def _strip_ns(tag: str) -> str:
    """Remove namespace prefix from XML tag."""
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def parse_message(xml_string: str) -> ParsedMessage:
    """Parse an XOpen XML message (V1 or V3) into a ParsedMessage."""
    msg = ParsedMessage(raw_xml=xml_string)
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return msg

    root_tag = _strip_ns(root.tag)

    if root_tag == "OWNMsg":
        _parse_v3(root, msg)
    elif root_tag == "OWNxml":
        _parse_v1(root, msg)
    else:
        # Unknown root, try V3-style parsing anyway
        _parse_v3(root, msg)

    return msg


def _parse_v3(root, msg: ParsedMessage):
    """Parse a V3 OWNMsg message."""
    payload = None
    for child in root:
        if _strip_ns(child.tag) == "Payload":
            payload = child
            break
    if payload is None:
        return

    for elem in payload:
        tag = _strip_ns(elem.tag)
        if tag == "Service":
            msg.service_type = elem.get("TYPE", "")
        elif tag == "SeqID":
            msg.seq_id = elem.get("ID", "")
            msg.progress = elem.get("Progress", "")
        elif tag == "Address":
            msg.who = elem.get("WHO", "")
            msg.where = elem.get("WHERE", "")
        elif tag == "ActionID":
            msg.action_id = elem.text or ""
        elif tag == "ParamList":
            for params_elem in elem:
                if _strip_ns(params_elem.tag) == "Params":
                    for k, v in params_elem.attrib.items():
                        msg.params[k] = v


def _parse_v1(root, msg: ParsedMessage):
    """Parse a V1 OWNxml message.

    V1 structure:
    <OWNxml>
      <Hdr>
        <MsgID><SID>...</SID><PID>...</PID></MsgID>
        <Dst><SysAddr><UniAddr><FCode>9006</FCode><UCode>9999</UCode>...
        <Src><SysAddr><UniAddr><FCode>9005</FCode><UCode>1</UCode>...
      </Hdr>
      <Info>...</Info>
      <Cmd>
        <WMsg>...</WMsg> or <RWMsg>... or <DBRetData>... etc.
      </Cmd>
    </OWNxml>
    """
    # Extract SID/PID from Hdr
    for hdr in root:
        if _strip_ns(hdr.tag) != "Hdr":
            continue
        for msg_id in hdr:
            if _strip_ns(msg_id.tag) == "MsgID":
                for field in msg_id:
                    ftag = _strip_ns(field.tag)
                    if ftag == "SID":
                        msg.seq_id = field.text or ""
                    elif ftag == "PID":
                        msg.progress = field.text or ""
        # Extract Src FCode/UCode
        for section in hdr:
            stag = _strip_ns(section.tag)
            if stag == "Src":
                _extract_addr_info(section, msg, prefix="src_")
            elif stag == "Dst":
                _extract_addr_info(section, msg, prefix="dst_")

    # Extract Cmd content
    for child in root:
        if _strip_ns(child.tag) == "Cmd":
            for cmd_child in child:
                cmd_tag = _strip_ns(cmd_child.tag)
                msg.action_id = cmd_tag  # WMsg, RWMsg, CWMsg, DBRetData, etc.
                # Extract all sub-elements and attributes as params
                _extract_all_params(cmd_child, msg.params)
            break


def _extract_addr_info(section, msg: ParsedMessage, prefix: str = ""):
    """Extract FCode/UCode from a Src or Dst XML section."""
    for elem in section.iter():
        tag = _strip_ns(elem.tag)
        if tag == "FCode" and elem.text:
            msg.params[prefix + "FCode"] = elem.text
        elif tag == "UCode" and elem.text:
            msg.params[prefix + "UCode"] = elem.text


def _extract_all_params(elem, params: dict, depth: int = 0):
    """Recursively extract all text content and attributes from an element."""
    # Attributes
    for k, v in elem.attrib.items():
        params[k] = v
    # Text content
    tag = _strip_ns(elem.tag)
    if elem.text and elem.text.strip():
        params[tag] = elem.text.strip()
    # Recurse into children
    if depth < 5:
        for child in elem:
            _extract_all_params(child, params, depth + 1)
