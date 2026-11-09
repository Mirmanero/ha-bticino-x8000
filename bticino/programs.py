"""Program profile codecs derived from Thermostat 1.3.11.

Slots refer to DAY/NIGHT/AWAY/PROTECTION presets, not literal temperatures.
Configuration decoding returns only temperature fields.
"""
import re
import math
import xml.etree.ElementTree as ET

from .protocol import program_file_name

DAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
MAX_PROGRAM_BYTES = 256 * 1024


def build_weekly_program(program_number: int, name: str, days: dict,
                         creation_date: str) -> dict:
    """Prepare an app-compatible full week without contacting the device."""
    from datetime import datetime
    program_file_name(program_number)
    if program_number == 0:
        raise ValueError("Program zero is reserved for the default profile")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError("Program name must contain 1 to 40 characters")
    if any(ord(c) < 32 for c in name):
        raise ValueError("Program name contains control characters")
    try:
        datetime.strptime(creation_date, "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        raise ValueError("Invalid program creation date") from None
    if not isinstance(days, dict) or set(days) != set(DAYS):
        raise ValueError("Exactly seven named weekdays are required")
    root = ET.Element("program_profile")
    ET.SubElement(root, "filename").text = program_file_name(program_number)
    description = ET.SubElement(root, "program_description")
    for tag, value in (("is_program_profile_valid", "TRUE"), ("number", str(program_number)),
                       ("name", name.strip()), ("type", "WEEKLY"),
                       ("is_creation_date_valid", "TRUE"), ("creation_date", creation_date)):
        ET.SubElement(description, tag).text = value
    weekday = ET.SubElement(root, "weekday")
    for day in DAYS:
        slots = days[day]
        # Eight slots is compatible with both older and newer firmware limits.
        if not isinstance(slots, list) or not 1 <= len(slots) <= 8:
            raise ValueError(f"Each day needs 1 to 8 slots: {day}")
        node = ET.SubElement(weekday, day)
        previous = None
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict) or set(slot) != {"time", "preset"}:
                raise ValueError(f"Slots require only time and preset: {day}")
            time, preset = slot["time"], slot["preset"]
            if not isinstance(time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
                raise ValueError(f"Invalid slot time: {day}")
            if (index == 0 and time != "00:00") or (previous is not None and time <= previous):
                raise ValueError(f"Slots must start at 00:00 and increase strictly: {day}")
            if preset not in ("DAY", "NIGHT", "AWAY", "PROTECTION"):
                raise ValueError(f"Unknown temperature preset: {day}")
            ET.SubElement(node, "slot", id=str(index), preset=preset, time=time)
            previous = time
    ET.indent(root, space="\t")
    content = ET.tostring(root, encoding="unicode") + "\n"
    return parse_program_file(content, program_number)


def program_slot_presence(params: dict, number: int) -> bool | None:
    """Absent/unknown metadata is never interpreted as a free slot."""
    value = params.get(f"program_{number}_present")
    if isinstance(value, str) and value.upper() in ("TRUE", "FALSE"):
        return value.upper() == "TRUE"
    return None


def parse_temperature_presets(content: str) -> dict:
    """Return an explicit allowlist; never expose raw config/network fields."""
    if len(content.encode("utf-8")) > MAX_PROGRAM_BYTES:
        raise ValueError("Configuration exceeds the read limit")
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise ValueError("Configuration DTD/entity declarations are not supported")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise ValueError("Invalid configuration XML") from None
    if root.tag != "configuration":
        raise ValueError("Response is not a configuration")
    settings = root.find("heating_and_cooling")
    if settings is None:
        raise ValueError("Temperature preset settings are missing")
    temperature_format = (root.findtext(".//temperature_format") or "").strip().upper()
    if temperature_format not in ("CELSIUS", "FAHRENHEIT"):
        raise ValueError("Configuration temperature format is missing or unsupported")
    result = {"temperature_format": temperature_format}
    for function in ("heating", "cooling"):
        presets = {}
        for preset in ("DAY", "NIGHT", "AWAY", "PROTECTION"):
            field = f"{function}_{preset.lower()}_temperature"
            try:
                value = float(settings.findtext(field, "").replace(",", "."))
                if not math.isfinite(value):
                    raise ValueError
            except ValueError:
                raise ValueError(f"Missing or invalid temperature field: {field}") from None
            presets[preset] = value
        result[function] = presets
    return result


def parse_program_file(content: str, program_number: int) -> dict:
    """Keep the original XML and return a summary without changing slot order."""
    expected_name = program_file_name(program_number)
    if len(content.encode("utf-8")) > MAX_PROGRAM_BYTES:
        raise ValueError("Program file exceeds the read limit")
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise ValueError("DTD/entity declarations are not supported in program files")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as err:
        raise ValueError("Thermostat returned invalid program XML") from err
    if root.tag != "program_profile":
        raise ValueError("Response is not a program_profile")
    if root.findtext("filename") != expected_name:
        raise ValueError("Returned program filename does not match the request")
    description = root.find("program_description")
    if description is None:
        raise ValueError("Program description is missing")
    if description.findtext("number") != str(program_number):
        raise ValueError("Returned program number does not match the request")
    weekday = root.find("weekday")
    if weekday is None:
        raise ValueError("Program weekday data is missing")
    days = {}
    for day in DAYS:
        slots = []
        for slot in weekday.findall(f"{day}/slot"):
            time = slot.get("time", "")
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
                raise ValueError(f"Invalid slot time in {day}")
            slots.append({"id": slot.get("id"), "time": time,
                          "preset": slot.get("preset")})
        days[day] = slots
    return {
        "program_number": program_number,
        "file_name": expected_name,
        "name": description.findtext("name"),
        "profile_type": description.findtext("type"),
        "valid": description.findtext("is_program_profile_valid") == "TRUE",
        "creation_date": description.findtext("creation_date"),
        "days": days,
        "xml": content,
    }
