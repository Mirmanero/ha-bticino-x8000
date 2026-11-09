"""HA WebSocket authorization, routing and API registration tests."""
import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

_resume = next((m for n, m in sys.modules.items() if n.endswith("test_resume_automatic")), None)
if _resume is None:
    _spec = importlib.util.spec_from_file_location("api_fixtures", Path(__file__).with_name("test_resume_automatic.py"))
    _resume = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_resume)
modules = _resume.modules


@pytest.fixture
def api(modules, monkeypatch):
    registry = {}
    ws = types.ModuleType("homeassistant.components.websocket_api")
    def websocket_command(schema):
        def decorate(fn):
            fn.schema = schema
            return fn
        return decorate
    ws.websocket_command = websocket_command
    ws.async_response = lambda fn: fn
    ws.async_register_command = MagicMock()
    http = types.ModuleType("homeassistant.components.http")
    http.StaticPathConfig = lambda url, path, cache_headers: types.SimpleNamespace(
        url_path=url, path=path, cache_headers=cache_headers)
    er = types.ModuleType("homeassistant.helpers.entity_registry")
    er.async_get = lambda hass: types.SimpleNamespace(async_get=lambda entity: registry.get(entity))
    for name in ("homeassistant.auth", "homeassistant.auth.permissions", "homeassistant.auth.permissions.const"):
        mod = types.ModuleType(name); mod.__path__ = []
        if name.endswith("const"): mod.POLICY_READ = "read"
        monkeypatch.setitem(sys.modules, name, mod)
    for mod in (ws, http, er):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setattr(sys.modules["homeassistant.components"], "websocket_api", ws, raising=False)
    monkeypatch.setattr(sys.modules["homeassistant.helpers"], "entity_registry", er, raising=False)
    module = importlib.import_module(modules.climate.__package__ + ".program_api")
    manager = types.SimpleNamespace(snapshot=MagicMock(return_value={"programs": []}),
        refresh=AsyncMock(return_value={"refreshed": True}), read=AsyncMock(return_value={"name": "test"}),
        save=AsyncMock(return_value={"saved": True}), activate=AsyncMock(return_value={"activated": True}),
        delete=AsyncMock(return_value={"deleted": True}))
    hass = types.SimpleNamespace(data={"bticino_thermostat": {"one": {"program_manager": manager}}},
        http=types.SimpleNamespace(async_register_static_paths=AsyncMock()))
    registry["climate.atrio"] = types.SimpleNamespace(config_entry_id="one", platform="bticino_thermostat")
    connection = types.SimpleNamespace(user=types.SimpleNamespace(is_admin=True,
        permissions=types.SimpleNamespace(check_entity=MagicMock(return_value=True))),
        send_error=MagicMock(), send_result=MagicMock())
    return types.SimpleNamespace(module=module, hass=hass, connection=connection,
        manager=manager, registry=registry, ws=ws)


def call(api, operation="list", **extra):
    message = {"id": 1, "type": "bticino_thermostat/programs", "entity_id": "climate.atrio", "operation": operation, **extra}
    asyncio.run(api.module.websocket_programs(api.hass, api.connection, message))


def test_static_path_and_commands_registered_only_once(api):
    asyncio.run(api.module.async_setup_program_api(api.hass))
    asyncio.run(api.module.async_setup_program_api(api.hass))
    assert api.hass.http.async_register_static_paths.call_count == 1
    assert api.ws.async_register_command.call_count == 1
    assert api.hass.http.async_register_static_paths.call_args.args[0][0].cache_headers is False


def test_entity_read_permission_is_required(api):
    api.connection.user.permissions.check_entity.return_value = False
    call(api)
    assert api.connection.send_error.call_args.args[1] == "unauthorized"
    api.manager.snapshot.assert_not_called()


@pytest.mark.parametrize("operation", ["save", "activate", "delete"])
def test_mutations_require_admin(api, operation):
    api.connection.user.is_admin = False
    call(api, operation, number=1, name="test", days={}, revision="revision")
    assert api.connection.send_error.call_args.args[1] == "unauthorized"
    getattr(api.manager, operation).assert_not_called()


def test_non_admin_can_read_catalog(api):
    api.connection.user.is_admin = False
    call(api)
    api.connection.send_result.assert_called_once_with(1, {"programs": []})


def test_wrong_platform_is_rejected(api):
    api.registry["climate.atrio"].platform = "another_integration"
    call(api)
    assert api.connection.send_error.call_args.args[1] == "not_found"
    api.manager.snapshot.assert_not_called()


def test_refresh_explicitly_calls_device_manager(api):
    call(api, refresh=True)
    api.manager.refresh.assert_awaited_once()
    api.connection.send_result.assert_called_once_with(1, {"refreshed": True})


def test_save_routes_revision_and_all_days(api):
    call(api, "save", number=1, name="test", days={"monday": []}, revision="known-hash")
    api.manager.save.assert_awaited_once_with(1, "test", {"monday": []}, "known-hash")


def test_transport_errors_never_expose_raw_details(api):
    api.manager.activate.side_effect = RuntimeError("SECRET_WIFI_PASSWORD")
    call(api, "activate", number=1)
    assert "SECRET" not in str(api.connection.send_error.call_args)
    api.connection.send_result.assert_not_called()


def test_websocket_schema_rejects_unknown_operation(api):
    try:
        import probatio as vol
    except ImportError:
        import voluptuous as vol
    schema = vol.Schema(api.module.websocket_programs.schema)
    with pytest.raises(Exception):
        schema({"type": "bticino_thermostat/programs", "operation": "raw_command", "entity_id": "climate.atrio"})


def load_integration(api, monkeypatch):
    from datetime import datetime
    const = sys.modules["homeassistant.const"]
    monkeypatch.setattr(const, "CONF_PORT", "port", raising=False)
    monkeypatch.setattr(const, "Platform", types.SimpleNamespace(
        CLIMATE="climate", SENSOR="sensor", SELECT="select", BUTTON="button"), raising=False)
    storage = types.ModuleType("homeassistant.helpers.storage")
    store = types.SimpleNamespace(async_load=AsyncMock(return_value={"backups": []}), async_save=AsyncMock())
    storage.Store = MagicMock(return_value=store)
    util = types.ModuleType("homeassistant.util"); util.__path__ = []
    util.dt = types.SimpleNamespace(now=datetime.now)
    monkeypatch.setitem(sys.modules, storage.__name__, storage)
    monkeypatch.setitem(sys.modules, util.__name__, util)
    root = Path(api.module.__file__).parent
    name = f"x8000_setup_test_{id(api.hass)}"
    spec = importlib.util.spec_from_file_location(name, root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    t = types.SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(),
        on_status_update=MagicMock(), on_disconnect=MagicMock())
    manager = types.SimpleNamespace(refresh=AsyncMock(), status_changed=MagicMock())
    module.Thermostat = MagicMock(return_value=t)
    module.ProgramManager = MagicMock(return_value=manager)
    api.hass.config_entries = types.SimpleNamespace(async_forward_entry_setups=AsyncMock(),
                                                   async_unload_platforms=AsyncMock(return_value=True))
    entry = types.SimpleNamespace(entry_id="two", data={"host": "offline.invalid", "pin": "fake-test-pin"})
    return module, t, store, entry


def test_integration_setup_and_unload_share_single_connection(api, monkeypatch):
    module, t, store, entry = load_integration(api, monkeypatch)
    assert asyncio.run(module.async_setup_entry(api.hass, entry)) is True
    assert "program_manager" in api.hass.data["bticino_thermostat"]["two"]
    t.connect.assert_awaited_once()
    assert "button" in api.hass.config_entries.async_forward_entry_setups.call_args.args[1]
    assert asyncio.run(module.async_unload_entry(api.hass, entry)) is True
    t.disconnect.assert_awaited_once()


def test_integration_closes_connection_when_platform_setup_fails(api, monkeypatch):
    module, t, store, entry = load_integration(api, monkeypatch)
    api.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("test failure")
    with pytest.raises(RuntimeError):
        asyncio.run(module.async_setup_entry(api.hass, entry))
    t.disconnect.assert_awaited_once()
    assert "two" not in api.hass.data["bticino_thermostat"]


def test_storage_load_failure_does_not_open_socket(api, monkeypatch):
    module, t, store, entry = load_integration(api, monkeypatch)
    store.async_load.side_effect = OSError("unavailable")
    with pytest.raises(OSError):
        asyncio.run(module.async_setup_entry(api.hass, entry))
    t.connect.assert_not_called()


def test_backups_are_saved_before_replacing_in_memory_history(api, monkeypatch):
    module, t, store, entry = load_integration(api, monkeypatch)
    store.async_load.return_value = {"backups": [{"old": n} for n in range(20)]}
    asyncio.run(module.async_setup_entry(api.hass, entry))
    callback = module.ProgramManager.call_args.args[1]
    asyncio.run(callback({"new": True}))
    history = store.async_save.call_args.args[0]["backups"]
    assert len(history) == 20 and history[0] == {"old": 1} and history[-1] == {"new": True}
