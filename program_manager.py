"""Device-backed program management, independent of HA's UI and storage APIs."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Callable

from .bticino import protocol
from .bticino.programs import build_weekly_program, program_slot_presence


class ProgramError(RuntimeError):
    """An actionable failure which is safe to show in the editor."""


class ProgramManager:
    """Serialize edits; device files, never HA timers, execute the schedules."""

    def __init__(self, thermostat, save_backup, clock: Callable = datetime.now):
        self.thermostat = thermostat
        self._save_backup = save_backup
        self._clock = clock
        self._lock = asyncio.Lock()
        self._listeners = []
        self._profiles = {}
        self._presence = {}
        self._temperatures = None
        self._temperature_warning = None
        self.last_error = None

    def subscribe(self, listener):
        self._listeners.append(listener)
        def unsubscribe():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return unsubscribe

    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    def status_changed(self, _status):
        self._notify()

    def snapshot(self):
        status = self.thermostat.status
        records = []
        for number, profile in sorted(self._profiles.items()):
            records.append({"number": number, "name": profile.get("name") or f"Program {number}",
                "valid": profile.get("valid", False), "read_only": number == 0,
                "revision": profile.get("sha256"), "type": profile.get("profile_type"),
                "error": profile.get("error")})
        return deepcopy({"programs": records,
            "free_slots": [n for n in range(1, 11) if self._presence.get(n) is False],
            "active_program": status.program_number, "mode": status.mode,
            "function": status.function, "connected": self.thermostat.connected,
            "temperatures": self._temperatures, "temperature_warning": self._temperature_warning,
            "error": self.last_error})

    async def refresh(self):
        async with self._lock:
            return await self._refresh()

    async def _refresh(self):
        try:
            await self.thermostat.get_status()
            presence = await self.thermostat.get_program_list()
            self._presence = {n: program_slot_presence(presence, n) for n in range(11)}
            profiles = {}
            for number, present in self._presence.items():
                if present is not True:
                    continue
                try:
                    profiles[number] = await self.thermostat.read_program(number)
                except Exception:
                    profiles[number] = {"name": f"Program {number}", "valid": False,
                        "error": "Program could not be read; refresh before editing"}
            self._profiles = profiles
            try:
                presets = await self.thermostat.read_temperature_presets(allow_unverified=True)
                self._temperatures = {key: presets[key] for key in ("temperature_format", "heating", "cooling")}
                self._temperature_warning = ("Configuration checksum is unverified" if
                    presets.get("checksum_verified") is not True else None)
            except Exception:
                self._temperatures = None
                self._temperature_warning = "Preset temperatures could not be read"
            self.last_error = None
        except Exception:
            self.last_error = "Thermostat is unavailable; refresh when connected"
            self._notify()
            raise ProgramError(self.last_error) from None
        self._notify()
        return self.snapshot()

    async def read(self, number: int):
        protocol.program_file_name(number)
        async with self._lock:
            profile = await self.thermostat.read_program(number)
            self._profiles[number] = profile
            self._notify()
            return deepcopy(profile)

    async def save(self, number: int, name: str, days: dict, revision: str | None):
        prepared = build_weekly_program(number, name, days,
            self._clock().strftime("%Y-%m-%dT%H:%M:%S"))
        async with self._lock:
            presence = await self.thermostat.get_program_list()
            occupied = program_slot_presence(presence, number)
            status = await self.thermostat.get_status()
            if occupied is None:
                raise ProgramError("Destination could not be checked; refresh before saving")
            if not occupied and status.program_number == number:
                raise ProgramError("Destination is reported active; refresh before creating a program")
            if occupied:
                if not revision:
                    raise ProgramError("Program slot is occupied; reload the program before editing")
                current = await self.thermostat.read_program(number)
                if current.get("checksum_verified") is not True or current["sha256"] != revision:
                    raise ProgramError("Program changed on the thermostat; reload before saving")
                # This must finish successfully before the first write to the device.
                await self._save_backup({"saved_at": self._clock().isoformat(), "reason": "edit",
                    "program": deepcopy(current)})
                # Preserve the profile's original creation date on ordinary edits.
                if current.get("creation_date"):
                    prepared = build_weekly_program(number, name, days, current["creation_date"])
            elif revision:
                raise ProgramError("Program was removed on the thermostat; reload before saving")
            self._profiles[number] = await self._write_and_verify(number, prepared)
            self._presence[number] = True
            await self.thermostat.get_status()
            self.last_error = None
            self._notify()
            return {"program": deepcopy(self._profiles[number]), "catalog": self.snapshot()}

    async def _write_and_verify(self, number, prepared):
        try:
            response = await self.thermostat._conn.send_command(
                protocol.build_set_program_file(number, prepared["xml"]))
            if not response or response.action_id != "AckMsg":
                raise ProgramError("Thermostat did not acknowledge the save")
            actual = await self.thermostat.read_program(number)
            keys = ("program_number", "name", "profile_type", "valid", "days")
            if actual.get("checksum_verified") is not True or any(actual[k] != prepared[k] for k in keys):
                raise ProgramError("Saved program could not be verified; refresh before retrying")
            return actual
        except ProgramError:
            raise
        except Exception:
            # Never retry an uncertain write automatically.
            raise ProgramError("Save outcome is unknown; refresh and inspect the program before retrying") from None

    async def activate(self, number: int):
        protocol.program_file_name(number)
        if number == 0:
            raise ProgramError("Select a user program from 1 to 10")
        async with self._lock:
            presence = await self.thermostat.get_program_list()
            if program_slot_presence(presence, number) is not True:
                raise ProgramError("Program is not present on the thermostat; refresh the list")
            profile = await self.thermostat.read_program(number)
            if not profile["valid"] or profile.get("checksum_verified") is not True:
                raise ProgramError("Program could not be verified and cannot be activated")
            status = await self.thermostat.get_status()
            if status.function not in ("HEATING", "COOLING"):
                raise ProgramError("Thermostat function is unknown; refresh before activating")
            accepted = await self.thermostat.set_mode("AUTOMATIC", function=status.function,
                                                       program_number=number)
            if not accepted:
                raise ProgramError("Thermostat rejected program activation")
            status = await self.thermostat.get_status()
            self._profiles[number] = profile
            self._notify()
            if status.mode != "AUTOMATIC" or status.program_number != number:
                raise ProgramError("Activation was not confirmed by the thermostat; refresh its status")
            return self.snapshot()

    async def delete(self, number: int, revision: str):
        protocol.program_file_name(number)
        if number == 0:
            raise ProgramError("The default program cannot be deleted")
        async with self._lock:
            status = await self.thermostat.get_status()
            if status.mode != "AUTOMATIC":
                raise ProgramError("Resume automatic mode before deleting programs")
            if status.program_number == number:
                raise ProgramError("Select another program before deleting the active one")
            current = await self.thermostat.read_program(number)
            if current.get("checksum_verified") is not True or current["sha256"] != revision:
                raise ProgramError("Program changed on the thermostat; reload before deleting")
            await self._save_backup({"saved_at": self._clock().isoformat(), "reason": "delete",
                                     "program": deepcopy(current)})
            try:
                response = await self.thermostat._conn.send_command(protocol.build_delete_program_file(number))
                if not response or response.action_id != "AckMsg":
                    raise ProgramError("Thermostat did not acknowledge deletion")
                slots = await self.thermostat.get_program_list()
                if program_slot_presence(slots, number) is not False:
                    raise ProgramError("Deletion could not be verified; refresh before retrying")
            except ProgramError:
                raise
            except Exception:
                raise ProgramError("Deletion outcome is unknown; refresh before retrying") from None
            self._profiles.pop(number, None)
            self._presence[number] = False
            self._notify()
            return self.snapshot()
