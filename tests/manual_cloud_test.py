"""Manual, real-account test for the cloud PIN extraction fix.

Not a pytest test (needs real credentials + network) -- run it directly:

    python -P tests\\manual_cloud_test.py

Reads credentials from tests/.cloud_credentials.json (gitignored):

    {"username": "you@example.com", "password": "..."}

Prints one line per gateway found (plant, description, mac, masked PIN)
so you can confirm every physical thermostat now gets its own PIN,
without ever printing full PINs/passwords into logs or chat.
"""
import importlib.util
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CREDS_PATH = pathlib.Path(__file__).resolve().parent / ".cloud_credentials.json"


def _load_cloud_module():
    spec = importlib.util.spec_from_file_location(
        "bticino_cloud_under_test", _REPO_ROOT / "bticino" / "cloud.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mask(secret: str) -> str:
    if not secret:
        return "(empty)"
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


def main() -> int:
    if not _CREDS_PATH.exists():
        print(f"Missing {_CREDS_PATH}. Create it with your username/password first.")
        return 1

    creds = json.loads(_CREDS_PATH.read_text(encoding="utf-8"))
    username = creds.get("username", "")
    password = creds.get("password", "")
    if not username or not password:
        print(f"{_CREDS_PATH} is missing username/password. Fill it in and re-run.")
        return 1

    cloud = _load_cloud_module()

    print(f"Logging in as {username}...")
    try:
        token = cloud.login(username, password)
    except cloud.CloudApiError as e:
        print(f"Login failed: {e}")
        return 1
    print("Login OK.")

    print("Fetching plants...")
    try:
        plants_data = cloud.get_plants(token)
    except cloud.CloudApiError as e:
        print(f"get_plants failed: {e}")
        return 1

    gateways = cloud.extract_plants_info(plants_data)

    print(f"\nFound {len(gateways)} gateway(s)/thermostat(s):\n")
    for g in gateways:
        print(
            f"  plant={g.plant_name!r} (id={g.plant_id})  "
            f"gateway_id={g.gateway_id}  description={g.description!r}  "
            f"mac={g.mac_address}  pin={_mask(g.psw_open)} (len={len(g.psw_open)})"
        )

    pins = [g.psw_open for g in gateways]
    unique_pins = set(pins)
    print(f"\n{len(pins)} gateway(s) total, {len(unique_pins)} unique PIN(s).")
    if len(gateways) > 1 and len(unique_pins) == 1:
        print("WARNING: multiple gateways but only one distinct PIN -- check raw JSON below.")
        print(json.dumps(plants_data, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
