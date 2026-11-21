"""Offline tests: climate entity lifecycle vs. the shared thermostat connection."""
import asyncio
import pathlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_resume_automatic import modules  # noqa: F401  (fixture)


def make_entity(m, conn):
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = conn
    t.disconnect = AsyncMock(side_effect=t.disconnect)
    entry = types.SimpleNamespace(data={"host": "offline.invalid"})
    entity = m.climate.BticinoClimateEntity(t, entry)
    entity.async_write_ha_state = MagicMock()
    return t, entity


def test_added_without_connection_does_not_raise(modules):
    # Thermostat disconnected (_conn None) while the platform adds the entity.
    _, entity = make_entity(modules, None)
    asyncio.run(entity.async_added_to_hass())


def test_added_with_connection_registers_reconnect_callback(modules):
    conn = types.SimpleNamespace(authenticated=True, on_connect=MagicMock(),
                                 send_command=AsyncMock(return_value=None))
    _, entity = make_entity(modules, conn)
    asyncio.run(entity.async_added_to_hass())
    conn.on_connect.assert_called_once_with(entity._on_connect)
