"""
High-level async API for interacting with a BTicino thermostat.

Event-driven: the thermostat pushes state updates via EVT messages.
The status property always reflects the latest known state.
"""
import logging
import hashlib
import xml.etree.ElementTree as ET
from typing import Callable, Optional

from .connection import XOpenConnection
from .models import ThermostatStatus, ParsedMessage
from . import protocol
from .programs import (parse_program_file, parse_temperature_presets,
                       build_weekly_program, program_slot_presence)

logger = logging.getLogger(__name__)


def _parse_status(params: dict) -> ThermostatStatus:
    """Build a ThermostatStatus from a message params dict."""
    status = ThermostatStatus()
    status.raw_params = dict(params)
    status.mode = params.get("mode")
    status.function = params.get("function")
    sp = params.get("setpoint")
    if sp:
        try:
            status.setpoint = float(sp)
        except ValueError:
            pass
    mt = params.get("measured_temperature")
    if mt:
        try:
            status.measured_temperature = float(mt)
        except ValueError:
            pass
    at = params.get("ambient_temperature_value")
    if at:
        try:
            status.ambient_temperature = float(at)
        except ValueError:
            pass
    ah = params.get("ambient_relative_humidity_value")
    if ah:
        try:
            status.ambient_humidity = float(ah)
        except ValueError:
            pass
    pn = params.get("program_number")
    if pn:
        try:
            status.program_number = int(pn)
        except ValueError:
            pass
    status.temperature_format = params.get("temperature_format", "CELSIUS")
    status.heating_load_state = params.get("heating_thermoregulation_load_state")
    status.cooling_load_state = params.get("cooling_thermoregulation_load_state")
    status.timestamp = params.get("timestamp")
    status.ip = params.get("ip")
    status.use_date_and_time_validity = params.get(
        "use_date_and_time_validity")
    status.init_date_and_time_validity = params.get(
        "init_date_and_time_validity")
    status.end_date_and_time_validity = params.get(
        "end_date_and_time_validity")
    status.is_device_date_and_time_valid = params.get(
        "is_device_date_and_time_valid")
    return status


class Thermostat:
    """BTicino thermostat async local control with push events.

    Usage:
        thermo = Thermostat("192.168.1.100", password="12345")
        thermo.on_status_update(lambda s: print(f"Update: {s}"))
        await thermo.connect()
        print(thermo.status)         # last known state
        status = await thermo.get_status()  # explicit GET
        await thermo.set_mode("MANUAL", setpoint=21.5)
        await thermo.disconnect()
    """

    def __init__(self, host: str, password: str = "",
                 port: int = 40000):
        self.host = host
        self.password = password
        self.port = port
        self._conn: Optional[XOpenConnection] = None
        self._status = ThermostatStatus()
        # Only device reports in AUTOMATIC identify a confirmed schedule.
        # Manual/protection reports may contain a placeholder program number.
        self._automatic_programs: dict[str, int] = {}
        self._status_callbacks: list[Callable[[ThermostatStatus], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []

    @property
    def connected(self) -> bool:
        return self._conn is not None and self._conn.authenticated

    @property
    def status(self) -> ThermostatStatus:
        """Last known thermostat status (updated by EVT push events)."""
        return self._status

    def on_status_update(self, callback: Callable[[ThermostatStatus], None]) -> None:
        """Register callback invoked when a device_state EVT arrives."""
        self._status_callbacks.append(callback)

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register callback for disconnection events."""
        self._disconnect_callbacks.append(callback)

    async def connect(self) -> None:
        """Connect, authenticate, and start listening for events."""
        self._conn = XOpenConnection(self.host, self.port, self.password)
        self._conn.on_event(self._handle_event)
        self._conn.on_disconnect(self._handle_disconnect)
        await self._conn.connect()
        logger.info("Thermostat ready at %s", self.host)

    async def disconnect(self) -> None:
        """Disconnect from the thermostat."""
        if self._conn:
            await self._conn.disconnect()
            self._conn = None

    async def get_status(self) -> ThermostatStatus:
        """Explicitly request current status via GET command."""
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
        msg = await self._conn.send_command(protocol.build_get_status())
        if not msg or msg.action_id != "device_state" or not msg.params:
            raise RuntimeError("Thermostat did not return device_state")
        self._update_status(msg.params)
        self._notify_status()
        return self._status

    def _notify_status(self) -> None:
        for cb in tuple(self._status_callbacks):
            try:
                cb(self._status)
            except Exception:
                logger.exception("Error in status update callback")

    def _update_status(self, params: dict) -> None:
        """Remember schedules confirmed by the device, separately by function."""
        self._status = _parse_status(params)
        status = self._status
        if (status.mode == "AUTOMATIC"
                and status.function in ("HEATING", "COOLING")
                and status.program_number is not None
                and status.program_number > 0):
            self._automatic_programs[status.function] = status.program_number

    async def set_mode(self, mode: str, setpoint: Optional[float] = None,
                       function: str = "HEATING",
                       program_number: Optional[int] = None,
                       boost_minutes: Optional[int] = None) -> bool:
        """Change thermostat mode. Returns True on ACK, False on NACK.

        For BOOST mode, boost_minutes (30, 60, or 90) is required.
        """
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
        if mode == "AUTOMATIC" and program_number is None:
            # Refresh first: the app may have selected a different schedule.
            # Never infer the active schedule from the first item in a list.
            await self.get_status()
            program_number = self._automatic_programs.get(function)
            if program_number is None:
                raise RuntimeError(
                    "No confirmed automatic program for " + function
                    + ". Resume the desired schedule in the Thermostat app "
                    "while this integration is connected, then retry.")
        msg = await self._conn.send_command(protocol.build_set_modality(
            mode=mode,
            function=function,
            setpoint=setpoint,
            program_number=program_number,
            boost_minutes=boost_minutes,
        ))
        if msg:
            logger.info("set_mode response: action=%s params=%s",
                        msg.action_id, msg.params)
            return msg.action_id == "AckMsg"
        return False

    async def get_program_list(self) -> Optional[dict]:
        """Read available program numbers."""
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
        msg = await self._conn.send_command(protocol.build_get_program_list(),
                                           expected_action="device_program_number_list")
        if msg and msg.action_id == "device_program_number_list":
            return msg.params
        raise RuntimeError("Thermostat did not return the program list")

    async def create_weekly_program(self, program_number: int, name: str, days: dict,
                                    creation_date: str) -> dict:
        """Create in a confirmed free slot, read back, and never activate it.

        Existing profiles and program zero cannot be overwritten by this method.
        A timeout after SET has an unknown outcome: callers must read, not retry.
        """
        prepared = build_weekly_program(program_number, name, days, creation_date)
        slots = await self.get_program_list()
        if program_slot_presence(slots, program_number) is not False:
            raise RuntimeError("Destination program is occupied or not confirmed free")
        status = await self.get_status()
        if status.program_number == program_number:
            raise RuntimeError("Destination program is currently active")
        msg = await self._conn.send_command(
            protocol.build_set_program_file(program_number, prepared["xml"]))
        if not msg or msg.action_id != "AckMsg":
            action = msg.action_id if msg else "no response"
            raise RuntimeError(f"Program creation not acknowledged: {action}; read before retrying")
        actual = await self.read_program(program_number)
        fields = ("program_number", "name", "profile_type", "valid", "days")
        verified = actual["checksum_verified"] is True and all(
            actual[key] == prepared[key] for key in fields)
        return {"acknowledged": True, "verified": verified,
                "activated_by_integration": False, "program": actual}

    async def read_program(self, program_number: int) -> dict:
        """Read one existing profile. Does not select, write, or delete it."""
        command = protocol.build_get_program_file(program_number)
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
        msg = await self._conn.send_command(command, expected_action="device_file")
        if not msg or msg.action_id != "device_file":
            action = msg.action_id if msg else "no response"
            raise RuntimeError(f"Program read failed: {action}")
        if msg.is_last.upper() != "TRUE":
            raise RuntimeError("Multipart program response is not supported yet")
        if msg.file_encoding:
            raise RuntimeError("Encoded or structured file response is not supported yet")
        if msg.file_data is None:
            raise RuntimeError("Program response contains no file_data")
        expected_name = protocol.program_file_name(program_number)
        received_name = msg.params.get("file_name", expected_name)
        if received_name not in (expected_name, f"/micro_fs/{expected_name}"):
            # Report identity fields only, not file contents or credentials.
            # Only accept the bare name or the device's observed /micro_fs path.
            # The embedded XML filename and program number are checked below.
            embedded_name = None
            embedded_number = None
            if (len(msg.file_data.encode("utf-8")) <= 256 * 1024
                    and "<!DOCTYPE" not in msg.file_data.upper()
                    and "<!ENTITY" not in msg.file_data.upper()):
                try:
                    root = ET.fromstring(msg.file_data)
                    embedded_name = root.findtext("filename")
                    embedded_number = root.findtext("program_description/number")
                except ET.ParseError:
                    pass

            def short(value):
                return repr(value[:200] if isinstance(value, str) else value)

            raise RuntimeError(
                "Program response filename does not match the request: "
                f"expected={expected_name!r}; "
                f"received={short(msg.params.get('file_name'))}; "
                f"embedded_filename={short(embedded_name)}; "
                f"embedded_program={short(embedded_number)}")
        try:
            content, checksum_form = protocol.checked_file_content(msg)
        except ValueError as err:
            raise RuntimeError(f"Program response {err}") from None
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        result = parse_program_file(content, program_number)
        result.update(sha256=digest, checksum_verified=True if checksum_form is not None else None)
        if checksum_form not in (None, "exact"):
            result["checksum_representation"] = checksum_form
        return result

    async def read_temperature_presets(self, allow_unverified: bool = False) -> dict:
        """Read only. The configuration stays in memory and is not returned/logged."""
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
        msg = await self._conn.send_command(
            protocol.build_get_temperature_presets(), expected_action="device_file")
        if not msg or msg.action_id != "device_file":
            raise RuntimeError("Temperature preset read failed: no configuration response")
        if msg.is_last.upper() != "TRUE" or msg.file_encoding or msg.file_data is None:
            raise RuntimeError("Temperature preset response is incomplete or unsupported")
        if msg.params.get("file_name") not in (
                None, "device_configuration.xml", "/micro_fs/device_configuration.xml"):
            raise RuntimeError("Temperature preset response is not the requested file")
        try:
            content, checksum_form = protocol.checked_file_content(msg)
        except ValueError as err:
            if not allow_unverified:
                raise RuntimeError(f"Temperature preset response {err}") from None
            # The official app's RetFileData path consumes the config without
            # checking sha256sum. Offer this explicitly for read-only diagnostics,
            # but never present the result as integrity-verified.
            result = parse_temperature_presets(msg.file_data)
            result["checksum_verified"] = False
            result["warning"] = "Configuration checksum mismatch; temperature values are unverified"
            return result
        result = parse_temperature_presets(content)
        result["checksum_verified"] = True if checksum_form is not None else None
        if checksum_form not in (None, "exact"):
            result["checksum_representation"] = checksum_form
        return result

    def _handle_event(self, msg: ParsedMessage) -> None:
        """Handle EVT messages from the connection's reader loop."""
        if msg.action_id == "device_state" and msg.params:
            self._update_status(msg.params)
            logger.info("EVT device_state update received")
            self._notify_status()
        else:
            logger.debug("EVT ignored: action=%s", msg.action_id)

    def _handle_disconnect(self) -> None:
        """Handle disconnection from the connection layer."""
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                logger.exception("Error in disconnect callback")
