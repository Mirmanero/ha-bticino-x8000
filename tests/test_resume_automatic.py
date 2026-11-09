"""Offline regressions: fake transport and minimal HA interface stubs.

No sockets, thermostat credentials, cloud calls, or Home Assistant install.
Run from outside the integration directory to avoid shadowing stdlib select.
"""
import asyncio
import importlib
import pathlib
import socket
import sys
import types
from enum import IntFlag, StrEnum
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = "x8000_offline_test"


@pytest.fixture
def modules(monkeypatch):
    # Windows creates a loopback socketpair when constructing its event loop.
    # Construct it before blocking connections; commands still use only mocks.
    runner = asyncio.Runner()
    runner.__enter__()
    monkeypatch.setattr(asyncio, "run", runner.run)
    def no_network(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(asyncio, "open_connection", no_network)
    pkg = types.ModuleType(PACKAGE)
    pkg.__path__ = [str(ROOT)]
    monkeypatch.setitem(sys.modules, PACKAGE, pkg)

    class Modes(StrEnum):
        OFF = "off"
        AUTO = "auto"
        HEAT = "heat"

    class Features(IntFlag):
        TARGET_TEMPERATURE = 1
        PRESET_MODE = 2

    class HAError(Exception):
        pass

    platform = types.SimpleNamespace(async_register_entity_service=MagicMock())

    interfaces = {
        "homeassistant": {}, "homeassistant.components": {},
        "homeassistant.components.climate": {
            "ClimateEntity": type("ClimateEntity", (), {}),
            "ClimateEntityFeature": Features, "HVACMode": Modes,
            "HVACAction": types.SimpleNamespace(OFF="off", HEATING="heating",
                                                COOLING="cooling", IDLE="idle")},
        "homeassistant.components.climate.const": {"PRESET_NONE": "none"},
        "homeassistant.components.select": {"SelectEntity": type("SelectEntity", (), {})},
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.const": {"ATTR_TEMPERATURE": "temperature", "CONF_HOST": "host",
                                "UnitOfTemperature": types.SimpleNamespace(CELSIUS="C")},
        "homeassistant.core": {"HomeAssistant": object, "callback": lambda fn: fn,
                               "SupportsResponse": types.SimpleNamespace(ONLY="only")},
        "homeassistant.exceptions": {"HomeAssistantError": HAError},
        "homeassistant.helpers": {},
        "homeassistant.helpers.entity_platform": {"AddEntitiesCallback": object,
                                                  "async_get_current_platform": lambda: platform},
    }
    for name, attrs in interfaces.items():
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, mod)
    result = types.SimpleNamespace(
        thermostat=importlib.import_module(PACKAGE + ".bticino.thermostat"),
        protocol=importlib.import_module(PACKAGE + ".bticino.protocol"),
        models=importlib.import_module(PACKAGE + ".bticino.models"),
        climate=importlib.import_module(PACKAGE + ".climate"),
        select=importlib.import_module(PACKAGE + ".select"),
        connection=importlib.import_module(PACKAGE + ".bticino.connection"),
        programs=importlib.import_module(PACKAGE + ".bticino.programs"),
        platform=platform,
        HAError=HAError, Modes=Modes)
    yield result
    runner.close()
    for name in list(sys.modules):
        if name.startswith(PACKAGE + "."):
            del sys.modules[name]


def setup_thermostat(m, state, replies=()):
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = types.SimpleNamespace(authenticated=True,
                                    send_command=AsyncMock(side_effect=list(replies)))
    t._update_status(state)
    return t


def response(m, action="AckMsg", **params):
    return m.models.ParsedMessage(service_type="RSP", action_id=action, params=params)


@pytest.mark.parametrize("override", ["MANUAL", "OFF", "PROTECTION", "BOOST"])
@pytest.mark.parametrize("function", ["HEATING", "COOLING"])
def test_resume_confirmed_schedule_after_override(modules, override, function):
    m = modules
    t = setup_thermostat(m, dict(mode="AUTOMATIC", function=function, program_number="3"))
    # A push update with a placeholder must not replace the automatic schedule.
    t._handle_event(m.models.ParsedMessage(
        service_type="EVT", action_id="device_state",
        params=dict(mode=override, function=function, program_number="0")))
    t._conn.send_command.side_effect = [
        response(m, "device_state", mode=override, function=function, program_number="0"),
        response(m)]
    assert asyncio.run(t.set_mode("AUTOMATIC", function=function)) is True
    messages = [m.protocol.parse_message(c.args[0]) for c in t._conn.send_command.call_args_list]
    assert messages[0].service_type == "GET"
    assert messages[1].service_type == "SET"
    assert messages[1].params == dict(temperature_format="CELSIUS", function=function,
        mode="AUTOMATIC", program_number="3", use_date_and_time_validity="FALSE",
        end_date_and_time_validity="", init_date_and_time_validity="")
    # ACK does not prove that a device applied a change. No optimistic mode update.
    assert t.status.mode == override


@pytest.mark.parametrize("number", [None, "0", "invalid"])
def test_unknown_program_never_sends_set(modules, number):
    m = modules
    params = dict(mode="PROTECTION", function="HEATING", program_number=number)
    t = setup_thermostat(m, params, [response(m, "device_state", **params)])
    with pytest.raises(RuntimeError, match="No confirmed automatic program"):
        asyncio.run(t.set_mode("AUTOMATIC"))
    assert t._conn.send_command.call_count == 1


def test_manual_program_number_is_not_proof_of_previous_schedule(modules):
    m = modules
    params = dict(mode="MANUAL", function="HEATING", program_number="9")
    t = setup_thermostat(m, params, [response(m, "device_state", **params)])
    with pytest.raises(RuntimeError, match="No confirmed automatic program"):
        asyncio.run(t.set_mode("AUTOMATIC"))
    assert t._conn.send_command.call_count == 1


def test_new_program_selected_in_app_replaces_cached_number(modules):
    m = modules
    t = setup_thermostat(m, dict(mode="AUTOMATIC", function="HEATING", program_number="2"),
        [response(m, "device_state", mode="AUTOMATIC", function="HEATING", program_number="7"),
         response(m)])
    asyncio.run(t.set_mode("AUTOMATIC"))
    sent = m.protocol.parse_message(t._conn.send_command.call_args.args[0])
    assert sent.params["program_number"] == "7"


def test_heating_schedule_not_reused_for_cooling(modules):
    m = modules
    t = setup_thermostat(m, dict(mode="AUTOMATIC", function="HEATING", program_number="2"),
        [response(m, "device_state", mode="PROTECTION", function="COOLING")])
    with pytest.raises(RuntimeError, match="No confirmed automatic program for COOLING"):
        asyncio.run(t.set_mode("AUTOMATIC", function="COOLING"))
    assert t._conn.send_command.call_count == 1


@pytest.mark.parametrize("action", ["NackMsg", "AckMsg", "unexpected"])
def test_only_ack_means_accepted(modules, action):
    m = modules
    t = setup_thermostat(m, {}, [response(m, action)])
    assert asyncio.run(t.set_mode("MANUAL", setpoint=20)) is (action == "AckMsg")


def test_failed_get_never_sends_automatic_set(modules):
    m = modules
    t = setup_thermostat(m, dict(mode="AUTOMATIC", function="HEATING", program_number="2"),
                        [response(m, "NackMsg")])
    with pytest.raises(RuntimeError, match="did not return device_state"):
        asyncio.run(t.set_mode("AUTOMATIC"))
    assert t._conn.send_command.call_count == 1


def test_explicit_program_remains_supported(modules):
    m = modules
    t = setup_thermostat(m, {}, [response(m)])
    assert asyncio.run(t.set_mode("AUTOMATIC", program_number=4))
    assert t._conn.send_command.call_count == 1
    assert m.protocol.parse_message(t._conn.send_command.call_args.args[0]).params["program_number"] == "4"


def entity(m, accepted=True):
    t = types.SimpleNamespace(
        status=m.models.ThermostatStatus(function="COOLING", mode="PROTECTION"),
        set_mode=AsyncMock(return_value=accepted))
    entry = types.SimpleNamespace(data={"host": "offline.invalid"})
    return m.climate.BticinoClimateEntity(t, entry), t


@pytest.mark.parametrize("command", ["off", "protection", "auto", "none", "heat", "temperature", "boost"])
def test_climate_preserves_function_and_surfaces_rejection(modules, command):
    m = modules
    e, t = entity(m, accepted=False)
    if command in ("off", "auto", "heat"):
        call = e.async_set_hvac_mode(m.Modes(command))
    elif command == "temperature":
        call = e.async_set_temperature(temperature=20)
    else:
        call = e.async_set_preset_mode("boost_30" if command == "boost" else command)
    with pytest.raises(m.HAError, match="did not acknowledge"):
        asyncio.run(call)
    assert t.set_mode.call_args.kwargs["function"] == "COOLING"
    assert t.status.mode == "PROTECTION"


def test_missing_schedule_error_is_visible_in_ha(modules):
    m = modules
    e, t = entity(m)
    t.set_mode.side_effect = RuntimeError("No confirmed automatic program")
    with pytest.raises(m.HAError, match="No confirmed automatic program"):
        asyncio.run(e.async_set_hvac_mode(m.Modes.AUTO))


def test_function_select_surfaces_rejection(modules):
    m = modules
    e, t = entity(m, accepted=False)
    select = m.select.BticinoFunctionSelect(t, e._entry)
    with pytest.raises(m.HAError, match="did not acknowledge"):
        asyncio.run(select.async_select_option("heating"))


def test_diagnostic_attributes(modules):
    e, t = entity(modules)
    t.status.program_number = 3
    t.status.use_date_and_time_validity = "FALSE"
    assert e.extra_state_attributes["program_number"] == 3
    assert e.extra_state_attributes["use_date_and_time_validity"] == "FALSE"
