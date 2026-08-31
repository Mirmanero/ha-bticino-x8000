"""Tests for bticino/cloud.py's gateway/PIN extraction.

Loaded by absolute file path (not via the `bticino` package) so these
tests don't depend on the repo root being importable -- the repo root
also contains a top-level select.py which would otherwise shadow the
stdlib `select` module during collection.
"""
import importlib.util
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CLOUD_PATH = _REPO_ROOT / "bticino" / "cloud.py"

_spec = importlib.util.spec_from_file_location("bticino_cloud_under_test", _CLOUD_PATH)
cloud = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cloud)

extract_plants_info = cloud.extract_plants_info


def _gateway(gateway_id, description, mac, psw):
    return {
        "GatewayID": gateway_id,
        "PswOpen": psw,
        "GatewayInfo": [
            {
                "MacAddress": mac,
                "PswOpen": psw,
                "LastPollingDate": "2026-08-24T23:13:58.000+0000",
                "Description": description,
            }
        ],
    }


def _plant(plant_id, plant_name, gateways):
    return {
        "PlantId": plant_id,
        "PlantName": plant_name,
        "Enabled": 1,
        "NumUsers": 1,
        "PlantInfo": [
            {
                "Address": "Via Roma 1, Italia",
                "PlantId": plant_id,
                "PlantName": plant_name,
                "Enabled": 1,
                "NumUsers": 1,
                "gatewayList": gateways,
            }
        ],
    }


def test_multiple_gateways_on_same_plant_each_get_own_pin():
    """Reproduces the reported issue: 3 thermostats on one plant."""
    data = [
        _plant(
            "P1",
            "Casa",
            [
                _gateway(111, "Primo Piano", "AA:AA:1", "pin-primo"),
                _gateway(222, "Secondo Piano", "AA:AA:2", "pin-secondo"),
                _gateway(333, "Piano Terra", "AA:AA:3", "pin-terra"),
            ],
        )
    ]

    results = extract_plants_info(data)

    assert len(results) == 3
    by_description = {r.description: r for r in results}
    assert by_description["Primo Piano"].psw_open == "pin-primo"
    assert by_description["Secondo Piano"].psw_open == "pin-secondo"
    assert by_description["Piano Terra"].psw_open == "pin-terra"
    # All three share the same plant, but keep distinct gateway identity.
    for r in results:
        assert r.plant_id == "P1"
        assert r.plant_name == "Casa"
    assert by_description["Primo Piano"].mac_address == "AA:AA:1"
    assert by_description["Primo Piano"].gateway_id == "111"


def test_single_gateway_plant_still_works():
    data = [_plant("P1", "Casa", [_gateway(111, "Casa", "AA:AA:1", "pin-only")])]

    results = extract_plants_info(data)

    assert len(results) == 1
    assert results[0].psw_open == "pin-only"
    assert results[0].plant_name == "Casa"


def test_multiple_plants_each_single_gateway():
    data = [
        _plant("P1", "Casa", [_gateway(111, "Casa", "AA:AA:1", "pin-casa")]),
        _plant("P2", "Ufficio", [_gateway(222, "Ufficio", "AA:AA:2", "pin-ufficio")]),
    ]

    results = extract_plants_info(data)

    assert len(results) == 2
    pins = {r.plant_name: r.psw_open for r in results}
    assert pins == {"Casa": "pin-casa", "Ufficio": "pin-ufficio"}


def test_gateway_without_psw_open_is_skipped():
    gateways = [_gateway(111, "Primo Piano", "AA:AA:1", "")]
    data = [_plant("P1", "Casa", gateways)]

    results = extract_plants_info(data)

    assert results == []


def test_legacy_shape_without_gateway_list_falls_back_to_recursive_search():
    data = [
        {
            "PlantId": "P1",
            "PlantName": "Casa",
            "SomeNestedThing": {"PswOpen": "legacy-pin"},
        }
    ]

    results = extract_plants_info(data)

    assert len(results) == 1
    assert results[0].psw_open == "legacy-pin"
    assert results[0].plant_name == "Casa"


@pytest.mark.parametrize("data", [None, []])
def test_empty_input_returns_empty_list(data):
    assert extract_plants_info(data) == []
