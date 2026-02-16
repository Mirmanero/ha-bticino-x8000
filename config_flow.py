"""Config flow for BTicino Thermostat integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import CONF_PIN, DEFAULT_PORT, DOMAIN
from .bticino.connection import (
    AuthenticationError,
    ConnectionError as BticinoConnectionError,
    XOpenConnection,
)
from .bticino.cloud import CloudApiError, fetch_local_password

_LOGGER = logging.getLogger(__name__)

CONF_RETRIEVE_FROM_CLOUD = "retrieve_from_cloud"


async def _test_connection(host: str, port: int, pin: str) -> None:
    """Test TCP connection and authentication. Raises on failure."""
    conn = XOpenConnection(host, port, pin)
    try:
        await conn.connect()
    finally:
        conn._auto_reconnect = False
        conn._closing = True
        await conn._close()


class BticinoThermostatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BTicino Thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str = ""
        self._pin: str = ""
        self._plants: list = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: IP and PIN."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._pin = user_input.get(CONF_PIN, "")

            # User wants to retrieve PIN from cloud
            if user_input.get(CONF_RETRIEVE_FROM_CLOUD, False):
                if not self._host:
                    errors[CONF_HOST] = "host_required"
                else:
                    return await self.async_step_cloud()

            elif not self._pin:
                errors[CONF_PIN] = "pin_required"

            else:
                # Test connection with provided PIN
                try:
                    await _test_connection(
                        self._host, DEFAULT_PORT, self._pin
                    )
                except AuthenticationError:
                    errors["base"] = "invalid_auth"
                except (BticinoConnectionError, OSError, asyncio.TimeoutError):
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error during connection test")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(self._host)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"BTicino Thermostat ({self._host})",
                        data={
                            CONF_HOST: self._host,
                            CONF_PORT: DEFAULT_PORT,
                            CONF_PIN: self._pin,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Optional(CONF_PIN, default=self._pin): str,
                    vol.Optional(CONF_RETRIEVE_FROM_CLOUD, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle cloud credentials step to retrieve PIN."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input["username"]
            password = user_input["password"]

            try:
                plants = await self.hass.async_add_executor_job(
                    fetch_local_password, username, password
                )
            except CloudApiError:
                errors["base"] = "invalid_cloud_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during cloud fetch")
                errors["base"] = "unknown"
            else:
                # Filter plants that have a password
                plants_with_pw = [p for p in plants if p.psw_open]
                if not plants_with_pw:
                    errors["base"] = "no_password_found"
                elif len(plants_with_pw) == 1:
                    self._pin = plants_with_pw[0].psw_open
                    return await self.async_step_user(
                        {CONF_HOST: self._host, CONF_PIN: self._pin}
                    )
                else:
                    self._plants = plants_with_pw
                    return await self.async_step_select_plant()

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle plant selection when multiple plants are found."""
        if user_input is not None:
            selected = user_input["plant"]
            for plant in self._plants:
                label = f"{plant.plant_name} ({plant.plant_id})"
                if label == selected:
                    self._pin = plant.psw_open
                    break
            return await self.async_step_user(
                {CONF_HOST: self._host, CONF_PIN: self._pin}
            )

        plant_options = [
            f"{p.plant_name} ({p.plant_id})" for p in self._plants
        ]

        return self.async_show_form(
            step_id="select_plant",
            data_schema=vol.Schema(
                {
                    vol.Required("plant"): vol.In(plant_options),
                }
            ),
        )
