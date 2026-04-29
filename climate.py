"""Climate platform for BTicino Thermostat."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import PRESET_NONE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, CONF_HOST, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .bticino.thermostat import Thermostat
from .bticino.models import ThermostatStatus

_LOGGER = logging.getLogger(__name__)

PRESET_PROTECTION = "protection"
PRESET_BOOST_30 = "boost_30"
PRESET_BOOST_60 = "boost_60"
PRESET_BOOST_90 = "boost_90"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BTicino Thermostat climate entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    thermostat: Thermostat = data["thermostat"]
    async_add_entities([BticinoClimateEntity(thermostat, entry)], True)


class BticinoClimateEntity(ClimateEntity):
    """Climate entity for a BTicino Smarther thermostat."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "bticino_thermostat"
    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 7.0
    _attr_max_temp = 40.0
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT]
    _attr_preset_modes = [
        PRESET_NONE, PRESET_BOOST_30, PRESET_BOOST_60, PRESET_BOOST_90,
        PRESET_PROTECTION,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(self, thermostat: Thermostat, entry: ConfigEntry) -> None:
        """Initialize the climate entity."""
        self._thermostat = thermostat
        self._entry = entry
        self._attr_unique_id = f"bticino_{entry.data[CONF_HOST]}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data[CONF_HOST])},
            "name": f"BTicino Thermostat ({entry.data[CONF_HOST]})",
            "manufacturer": "BTicino",
            "model": "Smarther Thermostat",
        }

    @property
    def available(self) -> bool:
        """Return True if the thermostat is connected."""
        return self._thermostat.connected

    @property
    def current_temperature(self) -> float | None:
        """Return the current measured temperature."""
        status = self._thermostat.status
        return status.ambient_temperature or status.measured_temperature

    @property
    def current_humidity(self) -> float | None:
        """Return the current measured humidity."""
        return self._thermostat.status.ambient_humidity

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._thermostat.status.setpoint

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        mode = self._thermostat.status.mode
        if mode is None or mode in ("OFF", "PROTECTION"):
            return HVACMode.OFF
        if mode == "AUTOMATIC":
            return HVACMode.AUTO
        # MANUAL and BOOST → HEAT (means "actively controlled")
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action based on load states."""
        status = self._thermostat.status
        if status.mode is None or status.mode == "OFF":
            return HVACAction.OFF
        if status.heating_load_state == "ON":
            return HVACAction.HEATING
        if status.cooling_load_state == "ON":
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode."""
        status = self._thermostat.status
        if status.mode == "BOOST":
            boost_time = status.raw_params.get("boostTime")
            if boost_time == "60":
                return PRESET_BOOST_60
            if boost_time == "90":
                return PRESET_BOOST_90
            return PRESET_BOOST_30
        if status.mode == "PROTECTION":
            return PRESET_PROTECTION
        return PRESET_NONE

    def _current_function(self) -> str:
        """Return the current function from thermostat status."""
        return self._thermostat.status.function or "HEATING"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (never changes function)."""
        if hvac_mode == HVACMode.OFF:
            await self._thermostat.set_mode(mode="OFF")
        elif hvac_mode == HVACMode.AUTO:
            await self._thermostat.set_mode(
                mode="AUTOMATIC",
                function=self._current_function(),
            )
        elif hvac_mode == HVACMode.HEAT:
            await self._thermostat.set_mode(
                mode="MANUAL",
                function=self._current_function(),
                setpoint=self._thermostat.status.setpoint,
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        await self._thermostat.set_mode(
            mode="MANUAL",
            function=self._current_function(),
            setpoint=temperature,
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        if preset_mode in (PRESET_BOOST_30, PRESET_BOOST_60, PRESET_BOOST_90):
            minutes = {
                PRESET_BOOST_30: 30,
                PRESET_BOOST_60: 60,
                PRESET_BOOST_90: 90,
            }[preset_mode]
            await self._thermostat.set_mode(
                mode="BOOST",
                function=self._current_function(),
                boost_minutes=minutes,
            )
        elif preset_mode == PRESET_PROTECTION:
            await self._thermostat.set_mode(mode="PROTECTION")
        elif preset_mode == PRESET_NONE:
            await self._thermostat.set_mode(
                mode="AUTOMATIC",
                function=self._current_function(),
            )

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass: connect and register callbacks."""
        self._thermostat.on_status_update(self._on_status_update)
        self._thermostat.on_disconnect(self._on_disconnect)
        self._thermostat._conn.on_connect(self._on_connect)

        try:
            await self._thermostat.get_status()
            self.async_write_ha_state()
        except Exception:
            _LOGGER.warning("Could not get initial status, waiting for push update")

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed: disconnect."""
        await self._thermostat.disconnect()

    @callback
    def _on_status_update(self, status: ThermostatStatus) -> None:
        """Handle push status update from thermostat."""
        self.async_write_ha_state()

    @callback
    def _on_disconnect(self) -> None:
        """Handle thermostat disconnection."""
        _LOGGER.warning("Thermostat disconnected")
        self.async_write_ha_state()

    @callback
    def _on_connect(self) -> None:
        """Handle thermostat reconnection."""
        _LOGGER.info("Thermostat reconnected")
        self.hass.async_create_task(self._async_refresh_after_reconnect())

    async def _async_refresh_after_reconnect(self) -> None:
        """Refresh status after reconnection."""
        try:
            await self._thermostat.get_status()
            self.async_write_ha_state()
        except Exception:
            _LOGGER.warning("Could not refresh status after reconnect")
