"""Authenticated HA WebSocket bridge for the bundled program editor."""
from pathlib import Path

try:
    import probatio as vol
except ImportError:  # HA releases before the schema-library migration.
    import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .program_manager import ProgramError

STATIC_URL = "/bticino_thermostat_static"


async def async_setup_program_api(hass):
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_program_api_registered"):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)
    ])
    websocket_api.async_register_command(hass, websocket_programs)
    data["_program_api_registered"] = True


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/programs",
    vol.Required("entity_id"): str,
    vol.Required("operation"): vol.In(("list", "get", "save", "activate", "delete")),
    vol.Optional("refresh", default=False): bool,
    vol.Optional("number"): int,
    vol.Optional("name"): str,
    vol.Optional("days"): dict,
    vol.Optional("revision"): vol.Any(str, None),
})
@websocket_api.async_response
async def websocket_programs(hass, connection, msg):
    entity_id = msg["entity_id"]
    operation = msg["operation"]
    user = connection.user
    if user is None or not user.permissions.check_entity(entity_id, POLICY_READ):
        connection.send_error(msg["id"], "unauthorized", "Entity access denied")
        return
    if operation in ("save", "activate", "delete") and not user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Program changes require an administrator")
        return
    entry = er.async_get(hass).async_get(entity_id)
    data = hass.data.get(DOMAIN, {}).get(entry.config_entry_id) if entry else None
    if (entry is None or entry.platform != DOMAIN or not entity_id.startswith("climate.")
            or not data or "program_manager" not in data):
        connection.send_error(msg["id"], "not_found", "BTicino thermostat is not loaded")
        return
    manager = data["program_manager"]
    try:
        if operation == "list":
            result = await manager.refresh() if msg.get("refresh") else manager.snapshot()
        else:
            if "number" not in msg:
                raise ProgramError("Program number is required")
            number = msg["number"]
            if operation == "get":
                result = {"program": await manager.read(number), "catalog": manager.snapshot()}
            elif operation == "save":
                if "name" not in msg or "days" not in msg:
                    raise ProgramError("Program name and seven weekdays are required")
                result = await manager.save(number, msg["name"], msg["days"], msg.get("revision"))
            elif operation == "activate":
                result = await manager.activate(number)
            else:
                if not msg.get("revision"):
                    raise ProgramError("Reload the program before deleting it")
                result = await manager.delete(number, msg["revision"])
    except (ProgramError, ValueError) as err:
        connection.send_error(msg["id"], "program_error", str(err))
        return
    except Exception:
        # Do not expose transport buffers, config fields or authentication data.
        connection.send_error(msg["id"], "program_error", "Operation failed; refresh before retrying")
        return
    connection.send_result(msg["id"], result)
