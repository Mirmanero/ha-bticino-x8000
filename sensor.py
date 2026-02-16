"""Sensor platform for BTicino Thermostat."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .bticino.thermostat import Thermostat
from .bticino.models import ThermostatStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BTicino Thermostat sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    thermostat: Thermostat = data["thermostat"]

    async_add_entities([
        BticinoTemperatureSensor(thermostat, entry),
        BticinoHumiditySensor(thermostat, entry),
        BticinoSetpointSensor(thermostat, entry),
    ])


class BticinoSensorBase(SensorEntity):
    """Base class for BTicino thermostat sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, thermostat: Thermostat, entry: ConfigEntry) -> None:
        self._thermostat = thermostat
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data[CONF_HOST])},
        }

    async def async_added_to_hass(self) -> None:
        """Register for push updates."""
        self._thermostat.on_status_update(self._on_status_update)

    @callback
    def _on_status_update(self, status: ThermostatStatus) -> None:
        """Handle push status update."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._thermostat.connected


class BticinoTemperatureSensor(BticinoSensorBase):
    """Ambient temperature sensor."""

    _attr_translation_key = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, thermostat: Thermostat, entry: ConfigEntry) -> None:
        super().__init__(thermostat, entry)
        self._attr_unique_id = f"bticino_{entry.data[CONF_HOST]}_temperature"

    @property
    def native_value(self) -> float | None:
        status = self._thermostat.status
        return status.ambient_temperature or status.measured_temperature


class BticinoHumiditySensor(BticinoSensorBase):
    """Ambient humidity sensor."""

    _attr_translation_key = "humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, thermostat: Thermostat, entry: ConfigEntry) -> None:
        super().__init__(thermostat, entry)
        self._attr_unique_id = f"bticino_{entry.data[CONF_HOST]}_humidity"

    @property
    def native_value(self) -> float | None:
        return self._thermostat.status.ambient_humidity


class BticinoSetpointSensor(BticinoSensorBase):
    """Setpoint temperature sensor."""

    _attr_translation_key = "setpoint"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, thermostat: Thermostat, entry: ConfigEntry) -> None:
        super().__init__(thermostat, entry)
        self._attr_unique_id = f"bticino_{entry.data[CONF_HOST]}_setpoint"

    @property
    def native_value(self) -> float | None:
        return self._thermostat.status.setpoint
