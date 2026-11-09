# Development changelog

## 1.3.0-beta.4 — unreleased

- Make the standalone Today card a compact dashboard strip: only the timeline, temperatures and hour axis, with no title or summary panels.
- Keep the full view in the editor; standalone users can opt in with `show_details: true`.

## 1.3.0-beta.3 — unreleased

- Display today's schedule as a proportional 00:00–24:00 timeline with preset colors, temperature labels and a current-time cursor.
- Tap or keyboard-select a period to inspect its exact times; keep the text list collapsed by default.

## 1.3.0-beta.2 — unreleased

- Simplify the editor with consultation first, explicit start/end periods, opt-in editing and secondary tools under More options.
- Add a read-only Today tab and standalone `custom:bticino-today-card`: saved active program, current/next period and actual target temperature.
- Use HA's time zone for day selection; update the display across schedule boundaries and midnight without thermostat polling.
- Keep Today independent of unsaved drafts; handle manual overrides, offline status and active-program changes explicitly.

## 1.3.0-beta.1 — unreleased

- Add a bundled Italian/English weekly-program dashboard card with responsive week timelines, day editing/copying, create/duplicate, JSON import/export, save verification and inactive-program deletion.
- Add native active-program select and refresh button; activation preserves the heating/cooling function.
- Read and write app-compatible XOpen V3 program files using WHO 1004, with verified profile read-back.
- Require fresh revisions before editing/deleting and persist up to 20 backups before writes. Do not retry uncertain writes.
- Serialize commands to handle replies without sequence IDs and keep waiting for file data after a preliminary ACK.
- Preserve the last confirmed automatic program by function and expose command rejections to HA.
- Add an explicit read-only path for preset values when configuration checksums are inconsistent, without exposing private configuration fields.

Create/read-back was tested on one X8000 Gen 1. The full HA card/native entities and edit/delete paths remain beta until supervised acceptance testing.
