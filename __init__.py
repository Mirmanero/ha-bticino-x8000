"""BTicino Thermostat integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PIN, DEFAULT_PORT, DOMAIN
from .bticino.thermostat import Thermostat

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BTicino Thermostat from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    pin = entry.data[CONF_PIN]

    thermostat = Thermostat(host, password=pin, port=port)

    try:
        await thermostat.connect()
    except Exception as err:
        # Raising ConfigEntryNotReady (instead of letting the raw
        # connection error propagate) tells Home Assistant this is a
        # transient failure: it will retry the setup automatically with
        # a growing backoff, rather than marking the entry as failed and
        # requiring the user to manually reload/reinstall it. This is
        # the common case right after a restart, when the gateway hasn't
        # released the previous session yet and briefly refuses new
        # connections.
        _LOGGER.warning("Failed to connect to thermostat at %s:%d: %s", host, port, err)
        raise ConfigEntryNotReady(
            f"Failed to connect to thermostat at {host}:{port}"
        ) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"thermostat": thermostat}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            thermostat: Thermostat = data["thermostat"]
            await thermostat.disconnect()

    return unload_ok
