"""
High-level async API for interacting with a BTicino thermostat.

Event-driven: the thermostat pushes state updates via EVT messages.
The status property always reflects the latest known state.
"""
import logging
from typing import Callable, Optional

from .connection import XOpenConnection
from .models import ThermostatStatus, ParsedMessage
from . import protocol

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
        if msg and msg.params:
            self._status = _parse_status(msg.params)
        return self._status

    async def set_mode(self, mode: str, setpoint: Optional[float] = None,
                       function: str = "HEATING",
                       program_number: Optional[int] = None,
                       boost_minutes: Optional[int] = None) -> bool:
        """Change thermostat mode. Returns True on ACK, False on NACK.

        For BOOST mode, boost_minutes (30, 60, or 90) is required.
        """
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
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
            return msg.action_id != "NackMsg"
        return False

    async def get_program_list(self) -> Optional[dict]:
        """Read available program numbers."""
        if not self._conn or not self._conn.authenticated:
            raise RuntimeError("Not connected. Call connect() first.")
        msg = await self._conn.send_command(protocol.build_get_program_list())
        if msg:
            return msg.params
        return None

    def _handle_event(self, msg: ParsedMessage) -> None:
        """Handle EVT messages from the connection's reader loop."""
        if msg.action_id == "device_state" and msg.params:
            self._status = _parse_status(msg.params)
            logger.info("EVT device_state update received")
            for cb in self._status_callbacks:
                try:
                    cb(self._status)
                except Exception:
                    logger.exception("Error in status update callback")
        else:
            logger.debug("EVT ignored: action=%s", msg.action_id)

    def _handle_disconnect(self) -> None:
        """Handle disconnection from the connection layer."""
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                logger.exception("Error in disconnect callback")
