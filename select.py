"""Select platform for BTicino Thermostat (HEATING/COOLING function)."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FUNCTION_HEATING, FUNCTION_COOLING
from .bticino.thermostat import Thermostat
from .bticino.models import ThermostatStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BTicino Thermostat select entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    thermostat: Thermostat = data["thermostat"]
    async_add_entities([BticinoFunctionSelect(thermostat, entry)])


class BticinoFunctionSelect(SelectEntity):
    """Select entity for HEATING/COOLING function."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "function_mode"
    _attr_options = [FUNCTION_HEATING, FUNCTION_COOLING]

    def __init__(self, thermostat: Thermostat, entry: ConfigEntry) -> None:
        self._thermostat = thermostat
        self._entry = entry
        self._attr_unique_id = f"bticino_{entry.data[CONF_HOST]}_function"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data[CONF_HOST])},
        }

    @property
    def available(self) -> bool:
        return self._thermostat.connected

    @property
    def current_option(self) -> str | None:
        function = self._thermostat.status.function
        if function == "COOLING":
            return FUNCTION_COOLING
        return FUNCTION_HEATING

    async def async_select_option(self, option: str) -> None:
        """Change the thermostat function while keeping the current mode."""
        new_function = "COOLING" if option == FUNCTION_COOLING else "HEATING"

        status = self._thermostat.status
        mode = status.mode or "AUTOMATIC"

        if mode in ("OFF", "PROTECTION"):
            # Just switch function, keep the mode as-is
            await self._thermostat.set_mode(
                mode=mode,
                function=new_function,
            )
        elif mode == "MANUAL":
            await self._thermostat.set_mode(
                mode="MANUAL",
                function=new_function,
                setpoint=status.setpoint,
            )
        elif mode == "BOOST":
            boost_time = int(status.raw_params.get("boostTime", 30))
            await self._thermostat.set_mode(
                mode="BOOST",
                function=new_function,
                boost_minutes=boost_time,
            )
        else:
            # AUTOMATIC or unknown
            await self._thermostat.set_mode(
                mode="AUTOMATIC",
                function=new_function,
            )

    async def async_added_to_hass(self) -> None:
        """Register for push updates."""
        self._thermostat.on_status_update(self._on_status_update)

    @callback
    def _on_status_update(self, status: ThermostatStatus) -> None:
        """Handle push status update."""
        self.async_write_ha_state()
