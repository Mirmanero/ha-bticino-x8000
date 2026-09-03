"""Config flow for BTicino Thermostat integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import CONF_PIN, DEFAULT_PORT, DOMAIN
from .bticino.connection import (
    AuthenticationError,
    ConnectionError as BticinoConnectionError,
    XOpenConnection,
)
from .bticino.cloud import CloudApiError, PlantInfo, fetch_local_password

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
        self._plants: list[PlantInfo] = []

        # State for the cloud -> cloud_gateway bulk-setup loop.
        self._cloud_gateways: list[PlantInfo] = []
        self._cloud_index: int = 0
        self._cloud_results: list[tuple[PlantInfo, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point: let the user choose cloud setup or manual entry."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    # ------------------------------------------------------------------
    # Manual setup: user already knows IP (+ optionally PIN).
    # ------------------------------------------------------------------

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup of a single thermostat: IP and PIN."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._pin = user_input.get(CONF_PIN, "")

            # User wants to retrieve PIN from cloud
            if user_input.get(CONF_RETRIEVE_FROM_CLOUD, False):
                if not self._host:
                    errors[CONF_HOST] = "host_required"
                else:
                    return await self.async_step_manual_cloud()

            elif not self._pin:
                errors[CONF_PIN] = "pin_required"

            else:
                # Test connection with provided PIN
                try:
                    await _test_connection(self._host, DEFAULT_PORT, self._pin)
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
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Optional(CONF_PIN, default=self._pin): str,
                    vol.Optional(CONF_RETRIEVE_FROM_CLOUD, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_manual_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle cloud credentials step to retrieve the PIN for one thermostat."""
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
                # Filter gateways that have a password
                plants_with_pw = [p for p in plants if p.psw_open]
                if not plants_with_pw:
                    errors["base"] = "no_password_found"
                elif len(plants_with_pw) == 1:
                    self._pin = plants_with_pw[0].psw_open
                    return await self.async_step_manual(
                        {CONF_HOST: self._host, CONF_PIN: self._pin}
                    )
                else:
                    self._plants = plants_with_pw
                    return await self.async_step_manual_select_plant()

        return self.async_show_form(
            step_id="manual_cloud",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def _gateway_label(plant: PlantInfo) -> str:
        """Build a human-readable label for a gateway (thermostat).

        A single plant can have several gateways (e.g. one X8000 per
        floor), each with its own Description ("Primo Piano", "Secondo
        Piano", ...). Include both the plant name and the gateway
        description so entries stay distinguishable in either case
        (multiple plants, or multiple gateways within one plant).
        """
        if plant.description and plant.description != plant.plant_name:
            return f"{plant.plant_name} - {plant.description}"
        return f"{plant.plant_name} ({plant.plant_id})"

    async def async_step_manual_select_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle gateway selection when multiple gateways/thermostats are found."""
        if user_input is not None:
            selected = user_input["plant"]
            for plant in self._plants:
                if self._gateway_label(plant) == selected:
                    self._pin = plant.psw_open
                    break
            return await self.async_step_manual(
                {CONF_HOST: self._host, CONF_PIN: self._pin}
            )

        plant_options = [self._gateway_label(p) for p in self._plants]

        return self.async_show_form(
            step_id="manual_select_plant",
            data_schema=vol.Schema(
                {
                    vol.Required("plant"): vol.In(plant_options),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Cloud-first bulk setup: log in once, then ask the local IP of
    # every gateway found on the account, one at a time.
    # ------------------------------------------------------------------

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask cloud credentials once, then walk every gateway found."""
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
                gateways = [p for p in plants if p.psw_open]
                if not gateways:
                    errors["base"] = "no_password_found"
                else:
                    self._cloud_gateways = gateways
                    self._cloud_index = 0
                    self._cloud_results = []
                    return await self.async_step_cloud_gateway()

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

    def _show_cloud_gateway_form(
        self, errors: dict[str, str] | None = None, host_default: str = ""
    ) -> ConfigFlowResult:
        current = self._cloud_gateways[self._cloud_index]
        return self.async_show_form(
            step_id="cloud_gateway",
            data_schema=vol.Schema(
                {vol.Optional(CONF_HOST, default=host_default): str}
            ),
            errors=errors or {},
            description_placeholders={
                "index": str(self._cloud_index + 1),
                "total": str(len(self._cloud_gateways)),
                "gateway_label": self._gateway_label(current),
            },
        )

    async def async_step_cloud_gateway(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for one gateway's local IP at a time; a blank IP skips it."""
        if user_input is not None:
            current = self._cloud_gateways[self._cloud_index]
            host = user_input.get(CONF_HOST, "").strip()

            if host:
                try:
                    await _test_connection(host, DEFAULT_PORT, current.psw_open)
                except AuthenticationError:
                    return self._show_cloud_gateway_form(
                        errors={"base": "invalid_auth"}, host_default=host
                    )
                except (BticinoConnectionError, OSError, asyncio.TimeoutError):
                    return self._show_cloud_gateway_form(
                        errors={"base": "cannot_connect"}, host_default=host
                    )
                except Exception:
                    _LOGGER.exception("Unexpected error during connection test")
                    return self._show_cloud_gateway_form(
                        errors={"base": "unknown"}, host_default=host
                    )
                self._cloud_results.append((current, host))

            self._cloud_index += 1

        if self._cloud_index >= len(self._cloud_gateways):
            return await self._async_create_bulk_entries()

        return self._show_cloud_gateway_form()

    async def _async_create_bulk_entries(self) -> ConfigFlowResult:
        """Create a config entry for every gateway that was tested successfully.

        One entry finishes this flow normally; the rest are created
        silently via SOURCE_IMPORT flows scheduled in the background,
        since their connection was already validated above and they
        don't need any further user interaction.
        """
        if not self._cloud_results:
            return self.async_abort(reason="no_devices_added")

        configured_hosts = {
            entry.data.get(CONF_HOST) for entry in self._async_current_entries()
        }
        new_results = [
            (gateway, host)
            for gateway, host in self._cloud_results
            if host not in configured_hosts
        ]
        if not new_results:
            return self.async_abort(reason="already_configured")

        foreground_gateway, foreground_host = new_results[0]
        for gateway, host in new_results[1:]:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={
                        CONF_HOST: host,
                        CONF_PORT: DEFAULT_PORT,
                        CONF_PIN: gateway.psw_open,
                    },
                )
            )

        await self.async_set_unique_id(foreground_host)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"BTicino Thermostat ({foreground_host})",
            data={
                CONF_HOST: foreground_host,
                CONF_PORT: DEFAULT_PORT,
                CONF_PIN: foreground_gateway.psw_open,
            },
        )

    async def async_step_import(
        self, import_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create an entry for a gateway already validated during bulk cloud setup."""
        host = import_info[CONF_HOST]
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"BTicino Thermostat ({host})",
            data=import_info,
        )
