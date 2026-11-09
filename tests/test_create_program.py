"""Offline tests for validated creation in a free slot; no device connections."""
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

_resume = next((m for n, m in sys.modules.items() if n.endswith("test_resume_automatic")), None)
if _resume is None:
    _spec = importlib.util.spec_from_file_location("create_fixtures", Path(__file__).with_name("test_resume_automatic.py"))
    _resume = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_resume)
modules = _resume.modules
DATE = "2026-10-26T14:41:40"


def week():
    return {day: ([{"time": "00:00", "preset": "PROTECTION"}] if day == "sunday" else [
        {"time": "00:00", "preset": "PROTECTION"}, {"time": "10:00", "preset": "DAY"},
        {"time": "11:00", "preset": "PROTECTION"}])
        for day in ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")}


def test_week_roundtrip_and_transition_meaning(modules):
    p = modules.programs.build_weekly_program(3, "HA Lun-Sab 10-11", week(), DATE)
    assert p["valid"] and p["profile_type"] == "WEEKLY"
    for day, slots in p["days"].items():
        assert len(slots) == (1 if day == "sunday" else 3)
        assert slots[0] == {"id": "0", "time": "00:00", "preset": "PROTECTION"}
        if day != "sunday":
            assert slots[1] == {"id": "1", "time": "10:00", "preset": "DAY"}
            assert slots[2] == {"id": "2", "time": "11:00", "preset": "PROTECTION"}


@pytest.mark.parametrize("bad", [0, 11, -1, True])
def test_create_rejects_reserved_or_invalid_number(modules, bad):
    with pytest.raises(ValueError):
        modules.programs.build_weekly_program(bad, "test", week(), DATE)


@pytest.mark.parametrize("bad_slots", [[], [{"time": "10:00", "preset": "DAY"}],
    [{"time": "00:00", "preset": "18"}],
    [{"time": "00:00", "preset": "DAY"}, {"time": "00:00", "preset": "NIGHT"}],
    [{"time": "00:00", "preset": "DAY"}, {"time": "24:00", "preset": "NIGHT"}],
    [{"time": "00:00", "preset": "DAY", "temperature": 18}],
    [{"time": f"{i:02}:00", "preset": "DAY"} for i in range(9)]])
def test_invalid_slots_cannot_be_serialized(modules, bad_slots):
    days = week()
    days["monday"] = bad_slots
    with pytest.raises(ValueError):
        modules.programs.build_weekly_program(3, "test", days, DATE)


def test_all_seven_days_required(modules):
    days = week()
    del days["sunday"]
    with pytest.raises(ValueError):
        modules.programs.build_weekly_program(3, "test", days, DATE)


def test_name_is_xml_escaped_and_utf8_hashed(modules):
    p = modules.programs.build_weekly_program(3, "Cinema & Caffè <prova>", week(), DATE)
    msg = modules.protocol.parse_message(modules.protocol.build_set_program_file(3, p["xml"]))
    assert (msg.service_type, msg.who, msg.action_id) == ("SET", "1004", "device_file")
    assert msg.params["file_name"] == "device_program_profile_3.xml"
    assert msg.file_data == p["xml"]
    assert msg.params["sha256sum"] == hashlib.sha256(p["xml"].encode()).hexdigest()
    assert modules.programs.parse_program_file(msg.file_data, 3)["name"] == "Cinema & Caffè <prova>"


@pytest.mark.parametrize("presence", ["TRUE", None, "unknown", "0"])
def test_never_overwrite_or_assume_missing_slot_is_free(modules, presence):
    m = modules
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = types.SimpleNamespace(authenticated=True, send_command=AsyncMock())
    t.get_program_list = AsyncMock(return_value={"program_3_present": presence})
    with pytest.raises(RuntimeError, match="occupied or not confirmed free"):
        asyncio.run(t.create_weekly_program(3, "test", week(), DATE))
    t._conn.send_command.assert_not_called()


def test_free_but_active_slot_is_not_written(modules):
    m = modules
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = types.SimpleNamespace(authenticated=True, send_command=AsyncMock())
    t.get_program_list = AsyncMock(return_value={"program_3_present": "FALSE"})
    t.get_status = AsyncMock(return_value=m.models.ThermostatStatus(program_number=3))
    with pytest.raises(RuntimeError, match="currently active"):
        asyncio.run(t.create_weekly_program(3, "test", week(), DATE))
    t._conn.send_command.assert_not_called()


@pytest.mark.parametrize("ack", ["AckMsg", "NackMsg"])
def test_creation_sends_one_file_and_never_a_mode_change(modules, ack):
    m = modules
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = types.SimpleNamespace(authenticated=True,
        send_command=AsyncMock(return_value=m.models.ParsedMessage(action_id=ack)))
    t.get_program_list = AsyncMock(return_value={"program_3_present": "FALSE"})
    t.get_status = AsyncMock(return_value=m.models.ThermostatStatus(program_number=2))
    p = m.programs.build_weekly_program(3, "test", week(), DATE)
    p["checksum_verified"] = True
    t.read_program = AsyncMock(return_value=p)
    if ack == "AckMsg":
        result = asyncio.run(t.create_weekly_program(3, "test", week(), DATE))
        assert result["verified"] and result["activated_by_integration"] is False
    else:
        with pytest.raises(RuntimeError, match="NackMsg"):
            asyncio.run(t.create_weekly_program(3, "test", week(), DATE))
        t.read_program.assert_not_called()
    assert t._conn.send_command.call_count == 1
    msg = m.protocol.parse_message(t._conn.send_command.call_args.args[0])
    assert msg.action_id == "device_file"


def test_readback_difference_is_not_success(modules):
    m = modules
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = types.SimpleNamespace(authenticated=True,
        send_command=AsyncMock(return_value=m.models.ParsedMessage(action_id="AckMsg")))
    t.get_program_list = AsyncMock(return_value={"program_3_present": "FALSE"})
    t.get_status = AsyncMock(return_value=m.models.ThermostatStatus(program_number=2))
    wrong = m.programs.build_weekly_program(3, "different", week(), DATE)
    wrong["checksum_verified"] = True
    t.read_program = AsyncMock(return_value=wrong)
    assert not asyncio.run(t.create_weekly_program(3, "test", week(), DATE))["verified"]
