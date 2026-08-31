"""
BTicino cloud API client for retrieving the local XOpen password (PswOpen).

The thermostat's local password is generated during commissioning and stored
in the cloud. The app fetches it via REST API when connecting locally.

API flow:
1. POST /eliot/users/sign_in -> auth_token in response headers
2. GET /eliot/plants/all -> JSON with PswOpen field per gateway
"""
import configparser
import json
import logging
import ssl
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

API_BASE = "https://www.myhomeweb.com"
LOGIN_URL = API_BASE + "/eliot/users/sign_in"
PLANTS_URL = API_BASE + "/eliot/plants/all"

# From decompiled app (main.cs lines 39258-39264)
PRJ_NAME = "CRO"
BRAND = "Bticino"
APP_VERSION = "legacy-1.3.10"


@dataclass
class PlantInfo:
    """Info about a single gateway (thermostat) within a plant (installation).

    A plant can have multiple gateways (e.g. one X8000 per floor/room), each
    with its own local password (PswOpen). One PlantInfo is produced per
    gateway found in the cloud response, not per plant.
    """
    plant_id: str = ""
    plant_name: str = ""
    psw_open: str = ""
    gateway_id: str = ""
    description: str = ""
    mac_address: str = ""
    raw: dict = field(default_factory=dict)


class CloudApiError(Exception):
    pass


def _ssl_ctx() -> ssl.SSLContext:
    """SSL context with verification disabled (same as the app)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def login(username: str, password: str) -> str:
    """Login to BTicino cloud and return auth_token.

    Args:
        username: Cloud account email
        password: Cloud account password

    Returns:
        auth_token string

    Raises:
        CloudApiError: on login failure
    """
    body = json.dumps({
        "username": username,
        "pwd": password,
        "appVersion": APP_VERSION,
        "brand": BRAND,
        "registrationId": "",
    }).encode("utf-8")

    req = urllib.request.Request(
        LOGIN_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "prj_name": PRJ_NAME,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as resp:
            token = resp.headers.get("auth_token", "")
            if not token:
                raise CloudApiError(
                    f"Login OK (HTTP {resp.status}) but no auth_token in headers")
            logger.info("Cloud login OK, token: %s...", token[:20])
            return token
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise CloudApiError(f"Login failed: HTTP {e.code} - {body_text}")


def get_plants(token: str) -> list[dict]:
    """Fetch all plants and gateways info from the cloud.

    Args:
        token: auth_token from login()

    Returns:
        Raw JSON list of plants

    Raises:
        CloudApiError: on API failure
    """
    req = urllib.request.Request(
        PLANTS_URL,
        headers={
            "auth_token": token,
            "prj_name": PRJ_NAME,
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            logger.info("Fetched %d plant(s) from cloud", len(data) if data else 0)
            return data
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise CloudApiError(f"API call failed: HTTP {e.code} - {body_text}")


def _find_passwords(data) -> list[str]:
    """Recursively search for PswOpen in any JSON structure."""
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in ("pswopen", "psw_open", "pwopen", "pw_open"):
                if value:
                    found.append(str(value))
            else:
                found.extend(_find_passwords(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_passwords(item))
    return found


def extract_plants_info(plants_data: list[dict]) -> list[PlantInfo]:
    """Extract gateway (thermostat) info with passwords from raw API response.

    A plant (installation) can contain several gateways under
    ``PlantInfo[].gatewayList[]`` -- typically one X8000 unit per
    floor/room -- and each gateway has its *own* local password
    (PswOpen). Previously only the first PswOpen found anywhere in the
    plant JSON was used, so users with more than one thermostat per
    plant only ever got a working PIN for one of them.

    Returns:
        List of PlantInfo, one per gateway found (not one per plant).
    """
    results = []
    if not plants_data:
        return results

    for plant in plants_data:
        plant_name = plant.get("PlantName", plant.get("plantName",
                     plant.get("Name", plant.get("name", ""))))
        plant_id = str(plant.get("PlantId", plant.get("plantId",
                   plant.get("Id", plant.get("id", "")))))

        plant_info_list = plant.get("PlantInfo", plant.get("plantInfo", []))
        if isinstance(plant_info_list, dict):
            plant_info_list = [plant_info_list]

        found_gateway = False

        for plant_info in plant_info_list or []:
            gateway_list = plant_info.get("gatewayList", plant_info.get("GatewayList", []))
            if isinstance(gateway_list, dict):
                gateway_list = [gateway_list]

            for gateway in gateway_list or []:
                gateway_id = str(gateway.get("GatewayID", gateway.get("gatewayId", "")))
                gateway_psw = gateway.get("PswOpen", "")

                gateway_info_list = gateway.get("GatewayInfo", gateway.get("gatewayInfo", []))
                if isinstance(gateway_info_list, dict):
                    gateway_info_list = [gateway_info_list]

                if gateway_info_list:
                    for gw_info in gateway_info_list:
                        info = PlantInfo(raw=gateway)
                        info.plant_id = plant_id
                        info.plant_name = plant_name
                        info.gateway_id = gateway_id
                        info.mac_address = gw_info.get("MacAddress", "")
                        info.description = gw_info.get("Description", "") or gateway_id
                        info.psw_open = gw_info.get("PswOpen", gateway_psw)
                        if info.psw_open:
                            results.append(info)
                            found_gateway = True
                elif gateway_psw:
                    info = PlantInfo(raw=gateway)
                    info.plant_id = plant_id
                    info.plant_name = plant_name
                    info.gateway_id = gateway_id
                    info.description = gateway_id
                    info.psw_open = gateway_psw
                    results.append(info)
                    found_gateway = True

        if not found_gateway:
            # Unknown/legacy response shape: fall back to a recursive
            # search for a single password, same as before.
            info = PlantInfo(raw=plant)
            info.plant_name = plant_name
            info.plant_id = plant_id
            info.gateway_id = str(plant.get("GatewayId", plant.get("gatewayId", "")))
            passwords = _find_passwords(plant)
            if passwords:
                info.psw_open = passwords[0]
                info.description = plant_name
                results.append(info)

    return results


def fetch_local_password(username: str, password: str) -> list[PlantInfo]:
    """Full flow: login to cloud and retrieve local PswOpen for all plants.

    Args:
        username: Cloud account email
        password: Cloud account password

    Returns:
        List of PlantInfo with psw_open populated

    Raises:
        CloudApiError: on any API failure
    """
    token = login(username, password)
    plants_data = get_plants(token)
    return extract_plants_info(plants_data)


def save_to_config(config_path: str, psw_open: str,
                   host: Optional[str] = None,
                   port: Optional[int] = None) -> None:
    """Save the retrieved password (and optionally host/port) to config.ini.

    Preserves existing values not being updated.
    """
    cfg = configparser.ConfigParser()
    cfg.read(config_path)

    if not cfg.has_section("thermostat"):
        cfg.add_section("thermostat")

    cfg.set("thermostat", "password", psw_open)

    if host is not None:
        cfg.set("thermostat", "host", host)
    if port is not None:
        cfg.set("thermostat", "port", str(port))

    with open(config_path, "w") as f:
        cfg.write(f)

    logger.info("Config saved to %s (password=%s)", config_path, psw_open)
