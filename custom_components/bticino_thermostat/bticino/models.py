"""Data models for BTicino thermostat state."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Mode(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"
    OFF = "OFF"
    BOOST = "BOOST"
    PROTECTION = "PROTECTION"


class Function(str, Enum):
    HEATING = "HEATING"
    COOLING = "COOLING"


@dataclass
class ThermostatStatus:
    function: Optional[str] = None
    mode: Optional[str] = None
    setpoint: Optional[float] = None
    temperature_format: str = "CELSIUS"
    program_number: Optional[int] = None
    use_date_and_time_validity: Optional[str] = None
    init_date_and_time_validity: Optional[str] = None
    end_date_and_time_validity: Optional[str] = None
    measured_temperature: Optional[float] = None
    ambient_temperature: Optional[float] = None
    ambient_humidity: Optional[float] = None
    heating_load_state: Optional[str] = None
    cooling_load_state: Optional[str] = None
    timestamp: Optional[str] = None
    ip: Optional[str] = None
    is_device_date_and_time_valid: Optional[str] = None
    raw_params: dict = field(default_factory=dict)

    def __str__(self) -> str:
        lines = []
        if self.mode:
            lines.append(f"  Modalita: {self.mode}")
        if self.function:
            lines.append(f"  Funzione: {self.function}")
        if self.setpoint is not None:
            lines.append(f"  Setpoint: {self.setpoint} {self.temperature_format}")
        if self.ambient_temperature is not None:
            lines.append(f"  Temperatura ambiente: {self.ambient_temperature}")
        elif self.measured_temperature is not None:
            lines.append(f"  Temperatura misurata: {self.measured_temperature}")
        if self.ambient_humidity is not None:
            lines.append(f"  Umidita' relativa: {self.ambient_humidity}%")
        if self.program_number is not None:
            lines.append(f"  Programma attivo: {self.program_number}")
        if self.heating_load_state:
            lines.append(f"  Riscaldamento: {self.heating_load_state}")
        if self.cooling_load_state:
            lines.append(f"  Raffreddamento: {self.cooling_load_state}")
        if self.use_date_and_time_validity and self.use_date_and_time_validity != "FALSE":
            lines.append(f"  Timer attivo: {self.use_date_and_time_validity}")
            if self.init_date_and_time_validity:
                lines.append(f"  Timer inizio: {self.init_date_and_time_validity}")
            if self.end_date_and_time_validity:
                lines.append(f"  Timer fine: {self.end_date_and_time_validity}")
        if self.timestamp:
            lines.append(f"  Timestamp: {self.timestamp}")
        if self.ip:
            lines.append(f"  IP: {self.ip}")
        return "\n".join(lines) if lines else "  (nessun dato)"


@dataclass
class ParsedMessage:
    """A parsed XOpen v3 message."""
    action_id: str = ""
    service_type: str = ""
    params: dict = field(default_factory=dict)
    seq_id: str = ""
    progress: str = ""
    who: str = ""
    where: str = ""
    raw_xml: str = ""
