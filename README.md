# BTicino Thermostat for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Mirmanero&repository=ha-bticino-x8000&category=integration)

Unofficial custom integration for [Home Assistant](https://www.home-assistant.io/) to control **BTicino Smarther** thermostats over the local network (XOpen V3 protocol).

> **Note:** This is an independent project, not affiliated with or supported by BTicino / Legrand. Use at your own risk.
>
> **Tested with BTicino X8000.** If you successfully use this integration with a different model, please [open an issue](https://github.com/Mirmanero/ha-bticino-x8000/issues) to let me know — I'd love to update the compatibility list.

## Features

- Local communication via TCP (XOpen V3 protocol with HMAC-SHA256 authentication)
- Push-based updates (no polling — the thermostat pushes state changes in real time)
- Automatic reconnection with exponential backoff
- Climate control: temperature setpoint, HVAC mode, preset modes
- Current temperature and humidity readings
- Cloud password retrieval (optional — retrieve the local PIN from BTicino cloud)
- Config Flow UI setup
- Italian and English translations

## Installation

### HACS (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Mirmanero&repository=ha-bticino-x8000&category=integration)

Click the button above, or add manually:

1. Open HACS in Home Assistant
2. Click the three dots menu (top right) → **Custom repositories**
3. Add `https://github.com/Mirmanero/ha-bticino-x8000` with category **Integration**
4. Search for **BTicino Thermostat** and install it
5. Restart Home Assistant

### Manual

1. Download or clone this repository
2. Copy all files into `config/custom_components/bticino_thermostat/`
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **BTicino Thermostat**
3. Enter:
   - **IP Address**: IP of your thermostat
   - **PIN**: Local XOpen password (leave empty to retrieve from cloud)
4. If you left the PIN empty, you'll be asked for your BTicino cloud credentials to retrieve it automatically

## Entities

### Climate

| Entity | Type | Description |
|--------|------|-------------|
| Thermostat | Climate | HVAC mode, target temperature, preset mode |

### Climate entity details

- **HVAC modes**: Off, Heat, Cool, Auto
- **Preset modes**: None, Boost (30 min), Protection
- **Temperature range**: 7–40 °C (0.5° step)
- **Current temperature**: Ambient temperature sensor
- **Current humidity**: Ambient humidity sensor
- **HVAC action**: Heating / Cooling / Idle / Off (based on load state)

## How it works

The integration communicates directly with the thermostat over TCP on your local network using the XOpen V3 protocol with HMAC-SHA256 authentication. The thermostat pushes status updates in real time via EVT messages — no polling is needed. A keep-alive mechanism ensures the connection stays active, with automatic reconnection on failure.

No internet connection or cloud service is required for normal operation. Cloud credentials are only needed once during setup if you don't know your local PIN.
