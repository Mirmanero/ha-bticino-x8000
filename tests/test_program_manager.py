"""Offline device simulation for program management and native HA selection."""
import asyncio
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

_resume = next((m for n, m in sys.modules.items() if n.endswith("test_resume_automatic")), None)
if _resume is None:
    _spec = importlib.util.spec_from_file_location("manager_fixtures", Path(__file__).with_name("test_resume_automatic.py"))
    _resume = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_resume)
modules = _resume.modules


def setup(m):
    import importlib
    module = importlib.import_module(m.climate.__package__ + ".program_manager")
    days = {d: [{"time": "00:00", "preset": "PROTECTION"}] for d in m.programs.DAYS}
    def profile(number, name):
        p = m.programs.build_weekly_program(number, name, days, "2026-10-26T10:00:00")
        p.update(sha256=hashlib.sha256(p["xml"].encode()).hexdigest(), checksum_verified=True)
        return p
    db = {1: profile(1, "Morning"), 2: profile(2, "Atrio")}
    state = m.models.ThermostatStatus(mode="AUTOMATIC", function="HEATING", program_number=2)
    t = types.SimpleNamespace(connected=True, status=state)
    events = []
    async def get_list():
        return {f"program_{n}_present": "TRUE" if n in db else "FALSE" for n in range(11)}
    async def read(number):
        events.append(("read", number))
        return deepcopy(db[number])
    async def send(xml):
        msg = m.protocol.parse_message(xml)
        events.append(("write", msg.params["file_name"]))
        number = int(msg.params["file_name"].split("_")[-1].split(".")[0])
        if msg.file_data == "ERASE":
            db.pop(number)
        else:
            p = m.programs.parse_program_file(msg.file_data, number)
            p.update(sha256=hashlib.sha256(msg.file_data.encode()).hexdigest(), checksum_verified=True)
            db[number] = p
        return m.models.ParsedMessage(action_id="AckMsg")
    async def activate(mode, function, program_number):
        state.mode, state.function, state.program_number = mode, function, program_number
        return True
    async def backup(value):
        events.append(("backup", value["program"]["program_number"]))
    t.get_program_list = AsyncMock(side_effect=get_list)
    t.read_program = AsyncMock(side_effect=read)
    t.get_status = AsyncMock(return_value=state)
    t.read_temperature_presets = AsyncMock(return_value={"temperature_format": "CELSIUS",
        "heating": {"DAY": 18, "NIGHT": 10, "AWAY": 10, "PROTECTION": 7},
        "cooling": {"DAY": 30, "NIGHT": 30, "AWAY": 30, "PROTECTION": 35}, "checksum_verified": False})
    t._conn = types.SimpleNamespace(send_command=AsyncMock(side_effect=send))
    t.set_mode = AsyncMock(side_effect=activate)
    saver = AsyncMock(side_effect=backup)
    manager = module.ProgramManager(t, saver, lambda: datetime(2026, 10, 26, 15, 0))
    return types.SimpleNamespace(manager=manager, t=t, db=db, events=events, saver=saver,
                                 days=days, module=module)


def test_catalog_names_free_slots_and_safe_temperature_summary(modules):
    f = setup(modules)
    result = asyncio.run(f.manager.refresh())
    assert [p["name"] for p in result["programs"]] == ["Morning", "Atrio"]
    assert result["free_slots"] == list(range(3, 11))
    assert result["active_program"] == 2
    assert result["temperature_warning"]
    assert "xml" not in repr(result)
    result["programs"][0]["name"] = "changed"
    assert f.manager.snapshot()["programs"][0]["name"] == "Morning"


def test_new_program_created_without_activation_or_backup_of_other_slot(modules):
    f = setup(modules)
    result = asyncio.run(f.manager.save(3, "New", f.days, None))
    assert result["program"]["name"] == "New"
    assert result["catalog"]["active_program"] == 2
    f.saver.assert_not_called()
    f.t.set_mode.assert_not_called()
    assert f.t._conn.send_command.call_count == 1


def test_existing_edit_persists_backup_before_first_write(modules):
    f = setup(modules)
    before = deepcopy(f.db[1])
    result = asyncio.run(f.manager.save(1, "Edited", f.days, before["sha256"]))
    assert result["program"]["name"] == "Edited"
    assert f.events.index(("backup", 1)) < next(i for i, e in enumerate(f.events) if e[0] == "write")
    assert f.saver.call_args.args[0]["program"]["xml"] == before["xml"]
    assert result["program"]["creation_date"] == before["creation_date"]


@pytest.mark.parametrize("revision", [None, "stale"])
def test_conflicting_edits_never_write(modules, revision):
    f = setup(modules)
    with pytest.raises(f.module.ProgramError):
        asyncio.run(f.manager.save(1, "Edited", f.days, revision))
    f.t._conn.send_command.assert_not_called()
    f.saver.assert_not_called()


def test_failed_backup_prevents_device_write(modules):
    f = setup(modules)
    f.saver.side_effect = OSError("disk full")
    with pytest.raises(OSError):
        asyncio.run(f.manager.save(1, "Edited", f.days, f.db[1]["sha256"]))
    f.t._conn.send_command.assert_not_called()


def test_save_with_unknown_slot_presence_is_blocked(modules):
    f = setup(modules)
    f.t.get_program_list.side_effect = None
    f.t.get_program_list.return_value = {}
    with pytest.raises(f.module.ProgramError, match="could not be checked"):
        asyncio.run(f.manager.save(3, "New", f.days, None))
    f.t._conn.send_command.assert_not_called()


def test_active_slot_is_not_treated_as_a_new_empty_program(modules):
    f = setup(modules)
    f.t.status.program_number = 3
    with pytest.raises(f.module.ProgramError, match="reported active"):
        asyncio.run(f.manager.save(3, "New", f.days, None))
    f.t._conn.send_command.assert_not_called()


def test_save_timeout_is_not_retried(modules):
    f = setup(modules)
    f.t._conn.send_command.side_effect = TimeoutError()
    with pytest.raises(f.module.ProgramError, match="outcome is unknown"):
        asyncio.run(f.manager.save(3, "New", f.days, None))
    assert f.t._conn.send_command.call_count == 1


def test_readback_checksum_failure_is_not_success(modules):
    f = setup(modules)
    f.t.read_program.side_effect = None
    bad = deepcopy(f.db[1]); bad["checksum_verified"] = False
    f.t.read_program.return_value = bad
    with pytest.raises(f.module.ProgramError, match="could not be verified"):
        asyncio.run(f.manager.save(3, "New", f.days, None))


def test_two_simultaneous_edits_use_revision_check(modules):
    f = setup(modules)
    revision = f.db[1]["sha256"]
    async def run():
        return await asyncio.gather(f.manager.save(1, "First", f.days, revision),
            f.manager.save(1, "Second", f.days, revision), return_exceptions=True)
    results = asyncio.run(run())
    assert isinstance(results[0], dict)
    assert isinstance(results[1], f.module.ProgramError)
    assert f.t._conn.send_command.call_count == 1


def test_activation_preserves_cooling_function(modules):
    f = setup(modules)
    f.t.status.function = "COOLING"
    result = asyncio.run(f.manager.activate(1))
    f.t.set_mode.assert_awaited_once_with("AUTOMATIC", function="COOLING", program_number=1)
    assert result["active_program"] == 1


def test_activation_requires_device_confirmation(modules):
    f = setup(modules)
    f.t.set_mode.side_effect = None
    f.t.set_mode.return_value = True
    with pytest.raises(f.module.ProgramError, match="not confirmed"):
        asyncio.run(f.manager.activate(1))


@pytest.mark.parametrize("number", [0, 2])
def test_default_and_active_profiles_are_not_deleted(modules, number):
    f = setup(modules)
    with pytest.raises(f.module.ProgramError):
        asyncio.run(f.manager.delete(number, "any"))
    f.t._conn.send_command.assert_not_called()


def test_delete_saves_backup_and_checks_presence(modules):
    f = setup(modules)
    result = asyncio.run(f.manager.delete(1, f.db[1]["sha256"]))
    assert 1 not in f.db and 1 in result["free_slots"]
    assert f.events.index(("backup", 1)) < next(i for i, e in enumerate(f.events) if e[0] == "write")
    msg = modules.protocol.parse_message(f.t._conn.send_command.call_args.args[0])
    assert msg.who == "1004" and msg.file_data == "ERASE"
    assert msg.params["sha256sum"] == hashlib.sha256(b"ERASE").hexdigest()


def test_delete_stale_revision_is_blocked(modules):
    f = setup(modules)
    with pytest.raises(f.module.ProgramError, match="changed"):
        asyncio.run(f.manager.delete(1, "old"))
    f.t._conn.send_command.assert_not_called()


def test_native_select_has_unique_names_and_selects_by_number(modules):
    f = setup(modules)
    f.db[1]["name"] = f.db[2]["name"] = "Same name"
    asyncio.run(f.manager.refresh())
    select = modules.select.BticinoProgramSelect(f.manager, types.SimpleNamespace(data={"host": "test"}))
    assert select.options == ["1 · Same name", "2 · Same name"]
    assert select.current_option == "2 · Same name"
    asyncio.run(select.async_select_option("1 · Same name"))
    assert select.current_option == "1 · Same name"
    f.t.status.mode = "MANUAL"
    assert select.current_option is None


def test_program_event_listener_can_be_removed(modules):
    f = setup(modules)
    changes = []
    remove = f.manager.subscribe(lambda: changes.append(1))
    f.manager.status_changed(f.t.status)
    remove(); f.manager.status_changed(f.t.status)
    assert changes == [1]
