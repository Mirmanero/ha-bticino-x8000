"""Offline test: removing the climate entity must not close the shared connection."""
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


def test_removing_climate_keeps_shared_connection(modules):
    # Sensors/selects/buttons share the thermostat: removing only the climate
    # entity must not close their connection.
    conn = types.SimpleNamespace(authenticated=True, disconnect=AsyncMock())
    t, entity = make_entity(modules, conn)
    # HA's Entity base class provides a no-op hook; the stub in these tests does not.
    remove = getattr(entity, "async_will_remove_from_hass", None)
    if remove:
        asyncio.run(remove())
    t.disconnect.assert_not_called()
