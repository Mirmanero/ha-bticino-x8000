"""Read-only program protocol tests. All files and replies below are synthetic."""
import asyncio
import hashlib
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# The runner stages these modules outside the HA package. Reuse its HA stubs
# and network-blocking fixture without importing the integration __init__.py.
_resume = next((m for n, m in sys.modules.items()
                if n.endswith("test_resume_automatic")), None)
if _resume is None:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "resume_fixtures", Path(__file__).with_name("test_resume_automatic.py"))
    _resume = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_resume)
modules = _resume.modules


def profile(number=3):
    days = "".join(f'<{d}><slot id="0" preset="NIGHT" time="00:00" />'
                   f'<slot id="1" preset="DAY" time="08:30" /></{d}>'
                   for d in ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"))
    return (f'<program_profile><filename>device_program_profile_{number}.xml</filename>'
            f'<program_description><number>{number}</number><name>Sala &amp; Cinema</name>'
            '<type>WEEKLY</type><is_program_profile_valid>TRUE</is_program_profile_valid>'
            '<creation_date>2026-10-26T12:00:00</creation_date></program_description>'
            f'<weekday>{days}</weekday></program_profile>')


def file_reply(m, content=None, checksum=True, service="RSP", seq="", **overrides):
    content = profile() if content is None else content
    digest = hashlib.sha256(content.encode()).hexdigest()
    sha = f' sha256sum="{digest}"' if checksum else ""
    xml = (f'<OWNMsg Profile="V3"><Payload><Service TYPE="{service}" />'
           f'<SeqID ID="{seq}" IsLast="TRUE" /><Address WHO="1004" />'
           '<ActionID>device_file</ActionID><ParamList>'
           f'<Params file_name="device_program_profile_3.xml"{sha} />'
           f'<Params><file_data encoded=""><![CDATA[{content}]]></file_data></Params>'
           '</ParamList></Payload></OWNMsg>')
    msg = m.protocol.parse_message(xml)
    for key, value in overrides.items():
        setattr(msg, key, value)
    return msg


def thermostat(m, reply):
    t = m.thermostat.Thermostat("offline.invalid")
    t._conn = types.SimpleNamespace(authenticated=True, send_command=AsyncMock(return_value=reply))
    return t


def test_get_file_matches_app_address_and_whitelist(modules):
    msg = modules.protocol.parse_message(modules.protocol.build_get_program_file(3))
    assert (msg.service_type, msg.who, msg.action_id) == ("GET", "1004", "device_file")
    assert msg.params == {"file_name": "device_program_profile_3.xml"}


@pytest.mark.parametrize("number", [-1, 11, True, 1.5, "3", "../device_configuration"])
def test_invalid_program_never_reaches_transport(modules, number):
    t = thermostat(modules, None)
    with pytest.raises(ValueError):
        asyncio.run(t.read_program(number))
    t._conn.send_command.assert_not_called()


@pytest.mark.parametrize("checksum", [True, False])
def test_file_read_preserves_xml_and_state(modules, checksum):
    m = modules
    t = thermostat(m, file_reply(m, checksum=checksum))
    original = t.status
    result = asyncio.run(t.read_program(3))
    assert result["xml"] == profile()
    assert result["name"] == "Sala & Cinema"
    assert result["checksum_verified"] is (True if checksum else None)
    assert result["days"]["monday"][1] == {"id": "1", "time": "08:30", "preset": "DAY"}
    assert t.status is original
    calls = t._conn.send_command.call_args_list
    assert len(calls) == 1
    assert m.protocol.parse_message(calls[0].args[0]).service_type == "GET"
    assert calls[0].kwargs == {"expected_action": "device_file"}


def test_cdata_crlf_is_preserved_for_checksum(modules):
    content = profile().replace("><", ">\r\n<")
    reply = file_reply(modules, content)
    assert reply.file_data == content
    result = asyncio.run(thermostat(modules, reply).read_program(3))
    assert result["checksum_verified"] is True


def test_namespaced_xopen_reply_keeps_file_content(modules):
    xml = file_reply(modules).raw_xml.replace('<OWNMsg Profile="V3">',
        '<OWNMsg xmlns="http://www.bticino.it/xopen/v1" Profile="V3">')
    reply = modules.protocol.parse_message(xml)
    assert asyncio.run(thermostat(modules, reply).read_program(3))["xml"] == profile()


def test_duplicate_file_payloads_are_rejected(modules):
    xml = file_reply(modules).raw_xml.replace('</ParamList>',
        '<Params><file_data encoded=""><![CDATA[extra]]></file_data></Params></ParamList>')
    reply = modules.protocol.parse_message(xml)
    with pytest.raises(RuntimeError, match="structured"):
        asyncio.run(thermostat(modules, reply).read_program(3))


@pytest.mark.parametrize("field,value,match", [
    ("is_last", "FALSE", "Multipart"),
    ("file_encoding", "base64", "Encoded"),
    ("file_data", None, "no file_data"),
    ("action_id", "NackMsg", "NackMsg"),
    ("action_id", "AckMsg", "AckMsg"),
])
def test_incomplete_or_unexpected_responses_fail(modules, field, value, match):
    msg = file_reply(modules, **{field: value})
    with pytest.raises(RuntimeError, match=match):
        asyncio.run(thermostat(modules, msg).read_program(3))


def test_hash_mismatch_is_rejected(modules):
    msg = file_reply(modules)
    msg.params["sha256sum"] = "0" * 64
    with pytest.raises(RuntimeError, match="SHA-256"):
        asyncio.run(thermostat(modules, msg).read_program(3))


def test_response_cannot_substitute_a_configuration_file(modules):
    msg = file_reply(modules)
    msg.params["file_name"] = "device_configuration.xml"
    with pytest.raises(RuntimeError, match="filename"):
        asyncio.run(thermostat(modules, msg).read_program(3))


@pytest.mark.parametrize("number", [0, 2, 10])
def test_micro_fs_reply_matches_the_observed_firmware_format(modules, number):
    msg = file_reply(modules, content=profile(number))
    msg.params["file_name"] = f"/micro_fs/device_program_profile_{number}.xml"
    result = asyncio.run(thermostat(modules, msg).read_program(number))
    assert result["program_number"] == number
    assert result["file_name"] == f"device_program_profile_{number}.xml"
    assert result["checksum_verified"] is True


@pytest.mark.parametrize("received", ["/micro_fs/device_program_profile_2.xml",
    "/micro_fs/../device_program_profile_3.xml", "/micro_fs/device_configuration.xml"])
def test_micro_fs_does_not_allow_another_file_or_path(modules, received):
    msg = file_reply(modules)
    msg.params["file_name"] = received
    with pytest.raises(RuntimeError, match="filename"):
        asyncio.run(thermostat(modules, msg).read_program(3))


@pytest.mark.parametrize("content,match", [
    (profile(2), "filename"),
    (profile().replace("<number>3</number>", "<number>2</number>"), "number"),
])
def test_micro_fs_outer_name_never_bypasses_inner_identity_checks(modules, content, match):
    msg = file_reply(modules, content=content)
    msg.params["file_name"] = "/micro_fs/device_program_profile_3.xml"
    with pytest.raises(ValueError, match=match):
        asyncio.run(thermostat(modules, msg).read_program(3))


@pytest.mark.parametrize("received", ["", "device_program_profile_03.xml", "/profiles/device_program_profile_3.xml",
                                    "device_program_profile_2.xml"])
def test_mismatch_reports_both_identities_without_accepting_the_file(modules, received):
    msg = file_reply(modules)
    msg.params["file_name"] = received
    with pytest.raises(RuntimeError) as error:
        asyncio.run(thermostat(modules, msg).read_program(3))
    text = str(error.value)
    assert "expected='device_program_profile_3.xml'" in text
    assert f"received={received!r}" in text
    assert "embedded_filename='device_program_profile_3.xml'" in text
    assert "embedded_program='3'" in text
    assert "Sala" not in text and "<program_profile" not in text


def test_mismatch_diagnostic_does_not_expand_xml_entities(modules):
    msg = file_reply(modules, content='<!DOCTYPE x [<!ENTITY x "private">]><x>&x;</x>')
    msg.params["file_name"] = "unexpected"
    with pytest.raises(RuntimeError) as error:
        asyncio.run(thermostat(modules, msg).read_program(3))
    assert "embedded_filename=None" in str(error.value)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("content,match", [
    ("<broken", "invalid program XML"),
    ("<configuration />", "not a program_profile"),
    (profile(2), "filename"),
    (profile().replace("<number>3</number>", "<number>4</number>"), "number"),
    (profile().replace("08:30", "24:00"), "slot time"),
    ('<!DOCTYPE x [<!ENTITY x "z">]>' + profile(), "DTD/entity"),
])
def test_bad_profile_is_rejected(modules, content, match):
    with pytest.raises(ValueError, match=match):
        modules.programs.parse_program_file(content, 3)


def connected(m):
    conn = m.connection.XOpenConnection("offline.invalid")
    conn._writer = types.SimpleNamespace(is_closing=lambda: False)
    conn._authenticated = True
    return conn


@pytest.mark.parametrize("service", ["RSP", "EVT"])
@pytest.mark.parametrize("with_seq", [True, False])
def test_ack_does_not_finish_file_request(modules, service, with_seq):
    m = modules
    async def scenario():
        c = connected(m)
        async def send(xml):
            seq = m.protocol.parse_message(xml).seq_id
            c._dispatch(m.models.ParsedMessage(service_type="RSP", action_id="AckMsg", seq_id=seq))
            assert len(c._pending) == 1
            c._dispatch(file_reply(m, service=service, seq=seq if with_seq else ""))
        c._write = AsyncMock(side_effect=send)
        result = await c.send_command(m.protocol.build_get_program_file(3), expected_action="device_file")
        assert result.action_id == "device_file"
        assert not c._pending
        assert not c._pending_actions
    asyncio.run(scenario())


def test_unrelated_state_event_does_not_finish_file_read(modules):
    m = modules
    async def scenario():
        c = connected(m)
        events = []
        c.on_event(events.append)
        async def send(xml):
            seq = m.protocol.parse_message(xml).seq_id
            event = m.models.ParsedMessage(service_type="EVT", action_id="device_state")
            c._dispatch(event)
            assert events == [event]
            assert len(c._pending) == 1
            c._dispatch(file_reply(m, seq=seq))
        c._write = AsyncMock(side_effect=send)
        await c.send_command(m.protocol.build_get_program_file(3), expected_action="device_file")
    asyncio.run(scenario())


def test_keepalive_cannot_overlap_file_transaction(modules):
    m = modules
    async def scenario():
        c = connected(m)
        sent = []
        async def send(xml):
            sent.append(m.protocol.parse_message(xml))
        c._write = AsyncMock(side_effect=send)
        read = asyncio.create_task(c.send_command(m.protocol.build_get_program_file(3), expected_action="device_file"))
        await asyncio.sleep(0)
        ping = asyncio.create_task(c.send_command(m.protocol.build_keep_alive()))
        await asyncio.sleep(0)
        assert len(sent) == 1
        c._dispatch(file_reply(m, seq=""))
        await read
        await asyncio.sleep(0)
        assert len(sent) == 2
        c._dispatch(m.models.ParsedMessage(service_type="RSP", action_id="AckMsg"))
        assert (await ping).action_id == "AckMsg"
    asyncio.run(scenario())


def test_file_read_nack_returns_immediately(modules):
    m = modules
    async def scenario():
        c = connected(m)
        async def send(xml):
            c._dispatch(m.models.ParsedMessage(service_type="RSP", action_id="NackMsg"))
        c._write = AsyncMock(side_effect=send)
        result = await c.send_command(m.protocol.build_get_program_file(3), expected_action="device_file")
        assert result.action_id == "NackMsg"
    asyncio.run(scenario())


def test_reply_with_foreign_sequence_is_not_assigned(modules):
    m = modules
    async def scenario():
        c = connected(m)
        async def send(xml):
            seq = m.protocol.parse_message(xml).seq_id
            c._dispatch(file_reply(m, seq="different-transaction"))
            assert len(c._pending) == 1
            c._dispatch(file_reply(m, seq=seq))
        c._write = AsyncMock(side_effect=send)
        assert (await c.send_command(m.protocol.build_get_program_file(3),
                                    expected_action="device_file")).action_id == "device_file"
    asyncio.run(scenario())


def test_file_timeout_cleans_transaction(modules):
    m = modules
    async def scenario():
        c = connected(m)
        c._write = AsyncMock()
        with pytest.raises(m.connection.ConnectionError, match="timeout"):
            await c.send_command(m.protocol.build_get_program_file(3), timeout=0.01, expected_action="device_file")
        assert not c._pending and not c._pending_actions
        assert not c._command_lock.locked()
    asyncio.run(scenario())


def test_xml_response_can_arrive_across_socket_reads(modules):
    m = modules
    c = connected(m)
    xml = file_reply(m).raw_xml
    for char in xml[:-1]:
        c._buffer += char
        assert c._extract_message() is None
    c._buffer += xml[-1:]
    assert m.protocol.parse_message(c._extract_message()).file_data == profile()


def test_ha_registers_read_action_with_response_and_validated_number(modules):
    m = modules
    entry = types.SimpleNamespace(entry_id="one", data={"host": "offline.invalid"})
    hass = types.SimpleNamespace(data={"bticino_thermostat": {"one": {"thermostat": object()}}})
    asyncio.run(m.climate.async_setup_entry(hass, entry, lambda *args: None))
    call = m.platform.async_register_entity_service.call_args_list[0]
    assert call.args[0] == "read_program"
    assert call.args[2] == "async_read_program"
    assert call.kwargs["supports_response"] == "only"
    import voluptuous as vol
    schema = vol.Schema(call.args[1])
    assert schema({"program_number": 3}) == {"program_number": 3}
    with pytest.raises(vol.Invalid):
        schema({"program_number": 11})


def test_ha_action_only_reads_and_returns_the_result(modules):
    m = modules
    t = thermostat(m, file_reply(m))
    entry = types.SimpleNamespace(data={"host": "offline.invalid"})
    e = m.climate.BticinoClimateEntity(t, entry)
    result = asyncio.run(e.async_read_program(3))
    assert result["program_number"] == 3
    assert m.protocol.parse_message(t._conn.send_command.call_args.args[0]).service_type == "GET"


def test_ha_reports_file_error(modules):
    m = modules
    t = thermostat(m, m.models.ParsedMessage(action_id="NackMsg"))
    e = m.climate.BticinoClimateEntity(t, types.SimpleNamespace(data={"host": "offline.invalid"}))
    with pytest.raises(m.HAError, match="Program read failed: NackMsg"):
        asyncio.run(e.async_read_program(3))


def configuration():
    values = {"heating": (18, 16, 14, 7), "cooling": (24, 26, 28, 35)}
    fields = "".join(f'<{function}_{preset}_temperature>{value}</{function}_{preset}_temperature>'
        for function, temperatures in values.items()
        for preset, value in zip(("day", "night", "away", "protection"), temperatures))
    return ('<configuration><network><wlan><ssid>SECRET_SSID</ssid>'
        '<password>SECRET_WIFI_PASSWORD</password><user_id>SECRET_USER</user_id></wlan></network>'
        '<geolocation><latitude>SECRET_LOCATION</latitude></geolocation>'
        '<temperature_format>CELSIUS</temperature_format>'
        f'<heating_and_cooling>{fields}</heating_and_cooling></configuration>')


def config_reply(m, **kwargs):
    msg = file_reply(m, content=configuration(), **kwargs)
    msg.params["file_name"] = "/micro_fs/device_configuration.xml"
    return msg


def test_temperature_presets_are_read_only_and_exclude_private_fields(modules, caplog):
    m = modules
    t = thermostat(m, config_reply(m))
    original = t.status
    result = asyncio.run(t.read_temperature_presets())
    assert result == {"temperature_format": "CELSIUS",
        "heating": {"DAY": 18, "NIGHT": 16, "AWAY": 14, "PROTECTION": 7},
        "cooling": {"DAY": 24, "NIGHT": 26, "AWAY": 28, "PROTECTION": 35},
        "checksum_verified": True}
    assert "SECRET" not in repr(result) + caplog.text
    assert "xml" not in result
    assert t.status is original
    call = t._conn.send_command.call_args
    request = m.protocol.parse_message(call.args[0])
    assert (request.service_type, request.action_id, request.who) == ("GET", "device_file", "1004")
    assert request.params == {"file_name": "device_configuration.xml"}


@pytest.mark.parametrize("original,replacement,match", [
    ("<heating_day_temperature>18", "<heating_day_temperature>nan", "temperature field"),
    ("<heating_day_temperature>18", "<heating_day_temperature>SECRET", "temperature field"),
    ("CELSIUS", "UNKNOWN", "temperature format"),
    ("<configuration>", '<!DOCTYPE x [<!ENTITY x "SECRET">]><configuration>', "DTD/entity"),
])
def test_configuration_errors_do_not_include_values(modules, original, replacement, match):
    content = configuration().replace(original, replacement)
    with pytest.raises(ValueError, match=match) as error:
        modules.programs.parse_temperature_presets(content)
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("field,value", [("file_encoding", "base64"), ("is_last", "FALSE"),
                                          ("file_data", None), ("action_id", "NackMsg")])
def test_incomplete_configuration_is_not_returned(modules, field, value):
    msg = config_reply(modules, **{field: value})
    with pytest.raises(RuntimeError) as error:
        asyncio.run(thermostat(modules, msg).read_temperature_presets())
    assert "SECRET" not in str(error.value)


def test_configuration_checksum_failure_does_not_leak_payload(modules):
    msg = config_reply(modules)
    msg.params["sha256sum"] = "0" * 64
    with pytest.raises(RuntimeError, match="checksum") as error:
        asyncio.run(thermostat(modules, msg).read_temperature_presets())
    assert "SECRET" not in str(error.value)


def test_presets_response_rejects_other_files(modules):
    msg = config_reply(modules)
    msg.params["file_name"] = "/micro_fs/device_program_profile_2.xml"
    with pytest.raises(RuntimeError, match="requested file"):
        asyncio.run(thermostat(modules, msg).read_temperature_presets())


def test_ha_returns_only_temperature_fields(modules):
    m = modules
    t = thermostat(m, config_reply(m))
    e = m.climate.BticinoClimateEntity(t, types.SimpleNamespace(data={"host": "offline.invalid"}))
    result = asyncio.run(e.async_read_temperature_presets())
    assert result["heating"]["DAY"] == 18
    assert "SECRET" not in repr(result)


def test_adjacent_cdata_sections_are_combined_exactly(modules):
    m = modules
    xml = config_reply(m).raw_xml.replace("SECRET_SSID", "SECRET_]]><![CDATA[SSID")
    msg = m.protocol.parse_message(xml)
    msg.params["file_name"] = "/micro_fs/device_configuration.xml"
    assert msg.file_data == configuration()
    result = asyncio.run(thermostat(m, msg).read_temperature_presets())
    assert result["checksum_verified"] is True
    assert "SECRET" not in repr(result)


def test_escaped_file_text_retains_crlf_for_checksum(modules):
    from xml.sax.saxutils import escape
    m = modules
    content = configuration().replace("><", ">\r\n<")
    msg = config_reply(m)
    xml = msg.raw_xml.replace('<![CDATA[' + configuration() + ']]>', escape(content))
    xml = xml.replace(msg.params["sha256sum"], hashlib.sha256(content.encode()).hexdigest())
    msg = m.protocol.parse_message(xml)
    msg.params["file_name"] = "/micro_fs/device_configuration.xml"
    assert msg.file_data == content
    assert asyncio.run(thermostat(m, msg).read_temperature_presets())["checksum_verified"] is True


@pytest.mark.parametrize("change", ["crlf", "trailing_lf", "bom", "outer_whitespace"])
def test_only_variants_matching_the_real_checksum_are_accepted(modules, change):
    m = modules
    content = configuration().replace("><", ">\n<")
    original = {"crlf": content.replace("\n", "\r\n"), "trailing_lf": content + "\n",
                "bom": "\ufeff" + content, "outer_whitespace": content}[change]
    delivered = "\n\t" + content + "\n" if change == "outer_whitespace" else content
    msg = config_reply(m)
    msg.file_data = delivered
    msg.params["sha256sum"] = hashlib.sha256(original.encode()).hexdigest()
    result = asyncio.run(thermostat(m, msg).read_temperature_presets())
    assert result["checksum_verified"] is True
    assert result["checksum_representation"] == "xml_whitespace_or_bom"
    assert result["heating"]["DAY"] == 18


def test_checksum_diagnostics_contain_no_configuration_values(modules):
    msg = config_reply(modules)
    msg.params["sha256sum"] = "0" * 64
    with pytest.raises(RuntimeError) as error:
        asyncio.run(thermostat(modules, msg).read_temperature_presets())
    text = str(error.value)
    assert "checksum_is_hex64=True" in text
    assert "cdata_sections=1" in text
    assert "replacement_chars=0" in text
    assert all(secret not in text for secret in ("SECRET", "<configuration", "<network", "password"))


@pytest.mark.parametrize("checksum", ["", "invalid", "a" * 63])
def test_invalid_checksum_format_is_not_accepted(modules, checksum):
    msg = config_reply(modules)
    msg.params["sha256sum"] = checksum
    with pytest.raises(RuntimeError, match="checksum_is_hex64=False"):
        asyncio.run(thermostat(modules, msg).read_temperature_presets())


def test_unverified_read_requires_explicit_option_and_marks_result(modules):
    msg = config_reply(modules)
    msg.params["sha256sum"] = "0" * 64
    result = asyncio.run(thermostat(modules, msg).read_temperature_presets(allow_unverified=True))
    assert result["checksum_verified"] is False
    assert "unverified" in result["warning"]
    assert result["heating"]["DAY"] == 18
    assert "SECRET" not in repr(result)


def test_unverified_option_still_rejects_wrong_file_and_bad_structure(modules):
    msg = config_reply(modules)
    msg.params["file_name"] = "wrong.xml"
    with pytest.raises(RuntimeError, match="requested file"):
        asyncio.run(thermostat(modules, msg).read_temperature_presets(allow_unverified=True))
    msg = config_reply(modules)
    msg.file_data = "<program_profile />"
    with pytest.raises(ValueError, match="not a configuration"):
        asyncio.run(thermostat(modules, msg).read_temperature_presets(allow_unverified=True))
