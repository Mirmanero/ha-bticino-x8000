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
    """Info about a plant (installation) from the cloud."""
    plant_id: str = ""
    plant_name: str = ""
    psw_open: str = ""
    gateway_id: str = ""
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
    """Extract plant info with passwords from raw API response.

    Returns:
        List of PlantInfo, one per plant found
    """
    results = []
    if not plants_data:
        return results

    for plant in plants_data:
        info = PlantInfo(raw=plant)
        info.plant_name = plant.get("PlantName", plant.get("plantName",
                          plant.get("Name", plant.get("name", ""))))
        info.plant_id = str(plant.get("PlantId", plant.get("plantId",
                        plant.get("Id", plant.get("id", "")))))
        info.gateway_id = str(plant.get("GatewayId", plant.get("gatewayId", "")))

        passwords = _find_passwords(plant)
        if passwords:
            info.psw_open = passwords[0]

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
