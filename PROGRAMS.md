# Weekly programs on the thermostat

The editor writes complete weekly profiles into the thermostat. Home Assistant does not send temperatures at every transition: the device executes the saved schedule independently.

This is a development build based on Mirmanero/ha-bticino-x8000, not an upstream release. Create/read-back was verified on one X8000 Gen 1 and the user reports the first HA beta works. The simplified editor and Today card in beta.2 have browser coverage; detailed device acceptance checks remain before a stable release.

## Install

1. Back up `custom_components/bticino_thermostat` outside `custom_components`.
2. Replace its complete contents with the development package, including `frontend/`, `program_manager.py`, `program_api.py`, and `button.py`.
3. Restart Home Assistant. Keep the existing integration/configuration; no PIN/account re-entry or thermostat reset is required. Re-enable the local integration if it was disabled for a separate VPN client.
4. Under **Settings → Dashboards → Resources**, add:
   - URL: `/bticino_thermostat_static/bticino-programs-card.js?v=1.3.0-beta.4`
   - Type: **JavaScript module**.
5. Reload the browser, then add **BTicino Programs** from the dashboard card picker and choose the climate entity. The visual configuration editor only needs the thermostat and an optional title.

For a YAML dashboard card:

```yaml
type: custom:bticino-programs-card
entity: climate.your_thermostat
```

For YAML-managed resources, add the same module URL to your existing Lovelace resources configuration instead of the UI. Use the resource mechanism supported by your HA version. Resource registration reference: https://contributors.home-assistant.io/frontend/custom-ui/resources/

The card is served by the integration; it is not copied into `www` and needs no frontend build or external CDN. Its file contains no credentials. Restart HA after backend changes; reload the browser after frontend updates. Change the URL version when upgrading to invalidate cached modules.

Italian installation/use guide: [PROGRAMS-IT.md](PROGRAMS-IT.md).

## Use

- The top menu activates a saved program, keeping the current heating/cooling function and cancelling manual overrides with `AUTOMATIC`.
- Select a program in the list to inspect its week and edit one day. Each slot marks the start of a preset until the next slot, or midnight at the end of that day.
- Consultation is the default: select a day to see explicit start/end periods, then use **Edit times** to change them. **Done editing** returns to consultation without saving. Confirm changes with **Save to thermostat**. Copying appears while editing; duplicate, import/export and deletion are under **More options**.
- Every day starts at `00:00`. Keep strictly increasing times; `24:00` is shown only as the end of a day, never entered as a slot.
- Create a program in a free device slot, duplicate one, or import a JSON export. Import creates a new draft in a free slot; it never overwrites a program by itself.
- Copy the current day to all days, weekdays, the weekend, or one specific day.
- Save validates the complete week, checks for edits made elsewhere, writes once and reads back the profile with its checksum. It does not automatically activate a new program.
- Editing an active program updates the schedule in use. The editor displays that fact before saving. Start testing with a duplicate or an inactive program.
- Delete asks for confirmation. Program zero, the active program and programs whose current revision cannot be verified cannot be deleted. Resume Automatic mode before deleting programs.
- Refresh reads names/profiles changed in the official app. No program polling loop or cloud API subscription is introduced.

## Today dashboard card

The editor has a **Today** tab. The same JavaScript resource also registers a separate read-only **BTicino Today** card with a visual entity picker:

```yaml
type: custom:bticino-today-card
entity: climate.your_thermostat
```

The standalone card defaults to **only a proportional 00:00-24:00 timeline**, with colored periods, temperature labels and a current-time cursor. No header, summary, legend or period list is shown. Exact ranges are available in segment tooltips and accessible labels. This compact strip is intended for dashboard composition.

The full view remains in the editor's Today tab. Add optional `show_details: true` to the standalone card YAML to enable it there too: it includes current/next-period summaries, the actual target and expandable period list. Both views always use the active saved profile, independently of the editor's selected program or unsaved draft. Use the editor's Refresh or the native Refresh programs button to retrieve external profile edits.

The display uses HA's configured time zone and the browser clock. It updates every 30 seconds and changes weekday at midnight without making device requests. A predicted period is not confirmation of the thermostat's clock or relay state. Manual/Boost/Protection/Off and unavailable states suppress the running highlight and next-period prediction; cached periods may still be shown for reference. Refresh to retrieve external profile edits. Active-program changes reported by the climate entity load the newly selected profile. Removing a card clears its display timer.

## Native entities

Each thermostat also gets:

- **Active program**, a native `select` whose options include the number and name, e.g. `2 · Programma Casa`. Names can repeat; numbers distinguish them.
- **Refresh programs**, a native button to reload programs edited in the app.

These can be added to an ordinary entities card or used with `select.select_option` and `button.press` in scripts/automations. Get their actual entity IDs from the thermostat device page; entity IDs depend on existing naming/registry settings.

When a manual/boost/protection override is active, the program select has no active option. Selecting a program explicitly returns the thermostat to Automatic.

The climate entity's last automatic-program memory is in RAM. After an HA restart during an override, explicitly choose a named program from the new select if the climate Auto command has no remembered program to resume.

## Temperature presets

Slots use `DAY`, `NIGHT`, `AWAY` and `PROTECTION`; they do not store an independent numeric temperature. The card shows the values read from the thermostat, for its current heating/cooling function. This build does not edit global preset temperatures because that would affect other programs too.

On the tested device, the program file's checksum is valid but the configuration file's advertised checksum differs consistently from its received contents. The official app's read-file path does not enforce that configuration checksum. The editor therefore uses the explicit read-only diagnostic path for the eight preset values, marks them as unverified, and asks the user to compare them with the official app. No network settings or complete configuration contents are returned to the browser or saved to disk.

The standalone `read_temperature_presets` action remains strict by default. Its explicit `allow_unverified: true` diagnostic option reports `checksum_verified: false` when applicable; no failed checksum is represented as verified. Program writes/read-back still require valid profile checksums.

## Conflicts, backups and connection loss

Before overwriting/deleting an existing program, its fresh device revision must match the one opened in the editor. A mismatch blocks the write and preserves the draft, allowing export before reloading.

The previous program is persisted before a write in HA storage under `bticino_thermostat_<config_entry_id>_program_backups`, keeping the last 20 snapshots per thermostat. These snapshots contain profile XML and metadata only, never the device configuration/PIN/cloud account. A storage failure aborts the write. This beta has JSON import/export in the UI; automatic rollback and a backup-history restore screen are not implemented.

After an ACK, the new program is read back and compared semantically, because the device may reformat XML. The profile checksum must be verified. A timeout after sending a write has an uncertain outcome: the editor instructs the user to refresh and inspect, never retries the write automatically.

There is no device-side atomic compare-and-swap command known for file updates. Revision checks protect against stale edits but cannot eliminate a concurrent change by another client between the final read and write. Avoid simultaneous app/HA edits to the same program.

Program operations share one command connection. On the tested X8000, a second local client was rejected while HA held the connection. For a separate VPN diagnostic client, disable the local HA integration and close local app sessions; ordinary use of this card uses HA's existing connection.

## Permissions and offline behavior

WebSocket reads require access to the selected entity. UI mutations require an HA administrator. The native select follows Home Assistant's standard entity/service permissions. Static card files contain no device credentials; all device operations run on the HA backend.

If HA or the editor is off, already stored programs keep running on the thermostat. Clock/time-zone behavior remains the device's responsibility; this integration does not change its clock, firmware, Wi-Fi settings or global temperature presets.

## Validation and contribution

Python tests use a simulated transport/HA interfaces and block outgoing connections. Browser tests use a local fake HA server and block external requests. They do not replace a full Home Assistant runtime/device acceptance test.

```text
python -m pip install -r requirements-dev.txt
python /absolute/path/to/repository/tests/run_offline.py
npm ci
npx playwright install chromium
npm run test:frontend
```

Run the Python script from outside the integration directory: the root `select.py` can shadow Python's standard-library module if the root is inserted into `sys.path`. The runner stages only test modules temporarily while keeping source lookups anchored to the checkout.

Browser tests write screenshots/results under `test-results/`, which is ignored. Set `X8000_TEST_OUTPUT_DIR` to choose another output directory. No Node packages are needed on HA; the shipped card is plain JavaScript.

### Acceptance checklist before a stable release

- Load the integration and card in a real HA instance; check native select/button names and permissions.
- Refresh and compare all names/slots with the app; verify the previously created test program.
- Create an inactive test program through the card; read it back; leave the existing schedule active.
- Edit that inactive program; check stale-revision conflict handling and the stored backup.
- Select a test program at a supervised time; verify the reported mode and number, then restore the intended program.
- Delete only an inactive test program; check that the active one remains unchanged.
- Cross an actual schedule boundary with HA stopped to verify device execution independently of HA.
- Remove the beta resource and restore the saved integration folder to roll back the UI/backend. Device programs are retained; restore any intentionally changed schedule via the app if needed.
