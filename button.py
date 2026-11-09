"""Manual local refresh of names/programs edited in the official app."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]["program_manager"]
    async_add_entities([BticinoRefreshProgramsButton(manager, entry)])


class BticinoRefreshProgramsButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "refresh_programs"
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, manager, entry):
        self._manager = manager
        self._attr_unique_id = f"bticino_{entry.data[CONF_HOST]}_refresh_programs"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.data[CONF_HOST])}}

    @property
    def available(self):
        return self._manager.thermostat.connected

    async def async_added_to_hass(self):
        self.async_on_remove(self._manager.subscribe(self.async_write_ha_state))

    async def async_press(self):
        try:
            await self._manager.refresh()
        except Exception as err:
            raise HomeAssistantError(str(err)) from err
