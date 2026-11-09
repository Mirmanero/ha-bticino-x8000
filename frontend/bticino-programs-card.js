/* BTicino program editor. The display clock never sends thermostat commands. */
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const PRESETS = ["DAY", "NIGHT", "AWAY", "PROTECTION"];
const LABELS = {
  it: { title: "Programmi settimanali", refresh: "Aggiorna", active: "Programma attivo", choose: "Scegli un programma",
    create: "Nuovo", duplicate: "Duplica", save: "Salva sul termostato", remove: "Elimina", activate: "Attiva questo programma",
    name: "Nome del programma", slot: "Numero", week: "La settimana", edit: "Fasce del giorno", add: "Aggiungi fascia",
    copy: "Copia questo giorno", all: "Tutta la settimana", weekdays: "Lunedì–venerdì", weekend: "Sabato e domenica",
    applyCopy: "Copia", discard: "Annulla modifiche", unsaved: "Modifiche da salvare", saved: "Programma salvato e verificato sul termostato.",
    loaded: "Programmi aggiornati.", activated: "Programma attivato.", deleted: "Programma eliminato.",
    empty: "Nessun programma disponibile. Premi Aggiorna per leggerli dal termostato.", loading: "Lettura dal termostato…",
    readOnly: "Programma predefinito: sola lettura.", activeEdit: "Questo programma è attivo: salvando aggiorni le fasce in uso.",
    selectFirst: "Seleziona un programma o creane uno nuovo.", protection: "Protezione", day: "Giorno", night: "Notte", away: "Fuori casa",
    manual: "Forzatura in corso", automatic: "Automatico", offline: "Termostato non collegato", presets: "Livelli del termostato",
    uncertain: "Temperature lette senza verifica del checksum: confrontale con l’app.", missingTemps: "Temperature non disponibili: sono mostrati i nomi dei livelli.",
    removeAsk: "Eliminare questo programma dal termostato? Verrà conservata una copia di sicurezza in Home Assistant.",
    discardAsk: "Scartare le modifiche non salvate?", export: "Esporta", import: "Importa", copyName: "Copia di", newName: "Nuovo programma",
    noSpace: "Tutti gli spazi sono occupati.", invalid: "Controlla nome e fasce: ogni giorno deve iniziare alle 00:00, con orari crescenti e al massimo 8 fasce.",
    invalidImport: "Il file non contiene un programma settimanale valido.", admin: "Per modificare i programmi serve un account amministratore.",
    note: "Gli orari vengono eseguiti dal termostato, anche con Home Assistant spento.", presetNote: "I livelli usano le temperature configurate sul termostato.",
    weekdaysLong: ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
    weekdaysShort: ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
    hour: "Ora", level: "Livello", deleteSlot: "Rimuovi fascia", copied: "Fasce copiate.", default: "Predefinito", entity: "Termostato", customTitle: "Titolo (facoltativo)" },
  en: { title: "Weekly programs", refresh: "Refresh", active: "Active program", choose: "Choose a program",
    create: "New", duplicate: "Duplicate", save: "Save to thermostat", remove: "Delete", activate: "Activate this program",
    name: "Program name", slot: "Number", week: "The week", edit: "Day slots", add: "Add slot", copy: "Copy this day",
    all: "Whole week", weekdays: "Monday–Friday", weekend: "Saturday and Sunday", applyCopy: "Copy", discard: "Discard changes",
    unsaved: "Unsaved changes", saved: "Program saved and verified on the thermostat.", loaded: "Programs refreshed.",
    activated: "Program activated.", deleted: "Program deleted.", empty: "No programs available. Refresh to read them from the thermostat.",
    loading: "Reading thermostat…", readOnly: "Default program: read only.", activeEdit: "This program is active: saving updates the schedule in use.",
    selectFirst: "Select a program or create a new one.", protection: "Protection", day: "Day", night: "Night", away: "Away",
    manual: "Override in progress", automatic: "Automatic", offline: "Thermostat disconnected", presets: "Thermostat levels",
    uncertain: "Preset temperatures have an unverified checksum: compare them with the app.",
    missingTemps: "Temperatures unavailable: preset names are shown.",
    removeAsk: "Delete this program from the thermostat? A backup will be kept in Home Assistant.", discardAsk: "Discard unsaved changes?",
    export: "Export", import: "Import", copyName: "Copy of", newName: "New program", noSpace: "All program slots are occupied.",
    invalid: "Check name and slots: each day must start at 00:00, with increasing times and at most 8 slots.", invalidImport: "This file is not a valid weekly program.",
    admin: "An administrator account is required to change programs.", note: "The thermostat runs the schedule even when Home Assistant is off.",
    presetNote: "Levels use temperatures configured on the thermostat.", weekdaysLong: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    weekdaysShort: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], hour: "Time", level: "Level", deleteSlot: "Remove slot", copied: "Slots copied.",
    default: "Default", entity: "Thermostat", customTitle: "Title (optional)" }
};
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clone = value => JSON.parse(JSON.stringify(value));
const minutes = time => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
Object.assign(LABELS.it, { today: "Oggi", programs: "Programmi", editDay: "Modifica fasce", done: "Fine modifica", more: "Altre opzioni", until: "fino alle", from: "Dalle", to: "Alle", now: "Adesso", next: "Prossima fascia", tomorrow: "Domani", daily: "La giornata", actual: "Obiettivo attuale", noActive: "Nessun programma automatico in esecuzione", paused: "Il programma è sospeso: è attiva una forzatura o un’altra modalità.", scheduled: "Fasce previste dal programma", timezone: "Orari di Home Assistant", fullDay: "Tutto il giorno", readProgram: "Programma da consultare", todayTitle: "Termostato · oggi", chooseDay: "Scegli un giorno per vedere le fasce. Premi Modifica fasce per cambiarle.", clockNote: "La fascia è calcolata dall’orario di HA; l’obiettivo attuale è riportato dal termostato.", review: "Salva le modifiche prima di attivare il programma." });
Object.assign(LABELS.en, { today: "Today", programs: "Programs", editDay: "Edit times", done: "Done editing", more: "More options", until: "until", from: "From", to: "To", now: "Now", next: "Next period", tomorrow: "Tomorrow", daily: "Today's schedule", actual: "Current target", noActive: "No automatic program running", paused: "The schedule is paused by an override or another mode.", scheduled: "Scheduled periods", timezone: "Home Assistant time", fullDay: "All day", readProgram: "Browse a program", todayTitle: "Thermostat · today", chooseDay: "Choose a day to see its periods. Use Edit times to change them.", clockNote: "The period is calculated using HA time; the current target is reported by the thermostat.", review: "Save changes before activating the program." });

class BticinoProgramsCard extends HTMLElement {
  constructor() {
    super(); this.attachShadow({ mode: "open" }); this._day = "monday"; this._busy = false; this._profiles = {}; this._view = "programs";
    this.shadowRoot.addEventListener("click", event => this._click(event));
    this.shadowRoot.addEventListener("input", event => this._input(event));
    this.shadowRoot.addEventListener("change", event => this._change(event));
  }
  connectedCallback() {
    if (!this._clockTimer) this._clockTimer = setInterval(() => {
      if (this._view === "today" && !this._busy) this._render();
    }, 30000);
  }
  disconnectedCallback() { clearInterval(this._clockTimer); this._clockTimer = null; }
  setConfig(config) {
    if (!config.entity || !config.entity.startsWith("climate.")) throw new Error("Choose a climate entity");
    const changed = this._config?.entity !== config.entity;
    this._config = { ...config }; if (changed) { this._generation = (this._generation || 0) + 1; this._catalog = null; this._draft = null; this._baseline = null; this._attempted = false; this._profiles = {}; this._editing = false; }
    this._render(); if (this._hass && changed && !this._busy) this._load();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const state = hass.states?.[this._config.entity];
    const signature = JSON.stringify([state?.state, state?.attributes?.program_number, state?.attributes?.program_mode, state?.attributes?.current_function, state?.attributes?.temperature, state?.attributes?.current_temperature, hass.language, hass.config?.time_zone]);
    if (this._catalog && state && signature !== this._signature) {
      this._catalog.active_program = state.attributes.program_number;
      this._catalog.mode = state.attributes.program_mode;
      this._catalog.function = state.attributes.current_function;
      this._catalog.connected = !["unavailable", "unknown"].includes(state.state);
    }
    if (!this._catalog && !this._busy && !this._attempted) this._load();
    else if (signature !== this._signature && !this._busy && (!this._dirty() || this._view === "today")) this._render();
    this._signature = signature;
    if (this._catalog && !this._busy && this._view === "today") this._ensureActive();
  }
  getCardSize() { return 10; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: 10, min_rows: 8 }; }
  static getConfigElement() { return document.createElement("bticino-programs-card-editor"); }
  static getStubConfig(hass, entities = []) {
    const entity = entities.find(id => id.startsWith("climate.") && hass.entities?.[id]?.platform === "bticino_thermostat") ||
      Object.keys(hass.states).find(id => id.startsWith("climate.") && "program_mode" in hass.states[id].attributes);
    return { entity: entity || "" };
  }
  _t(key) { return LABELS[this._hass?.language?.startsWith("it") ? "it" : "en"][key]; }
  _admin() { return this._hass?.user?.is_admin === true; }
  _dirty() { return !!this._draft && JSON.stringify(this._draft) !== this._baseline; }
  _readOnly() { return !this._admin() || this._draft?.number === 0; }
  _canLeave() { return !this._dirty() || window.confirm(this._t("discardAsk")); }
  _api(operation, extra = {}) {
    const generation = this._generation;
    return this._hass.callWS({ type: "bticino_thermostat/programs", entity_id: this._config.entity, operation, ...extra }).then(result => {
      if (generation !== this._generation) throw new Error("Thermostat changed");
      return result;
    });
  }
  async _run(task) {
    if (this._busy) return;
    const generation = this._generation;
    this._busy = true; this._error = ""; this._message = ""; this._render();
    try { await task(); }
    catch (err) { if (generation === this._generation) this._error = this._friendlyError(err.message || String(err)); }
    finally { this._busy = false; this._render(); if (generation !== this._generation && !this._catalog) this._load(); }
  }
  _friendlyError(message) {
    if (!this._hass?.language?.startsWith("it")) return message;
    const known = {
      "Program changed on the thermostat; reload before saving": "Il programma è cambiato sul termostato. Ricaricalo prima di salvare.",
      "Program slot is occupied; reload the program before editing": "Lo spazio è stato occupato da un altro programma. Aggiorna l’elenco.",
      "Thermostat is unavailable; refresh when connected": "Il termostato non è raggiungibile. Riprova con Aggiorna quando è collegato.",
      "Select another program before deleting the active one": "Attiva un altro programma prima di eliminare questo.",
      "Program changes require an administrator": this._t("admin"),
      "Save outcome is unknown; refresh and inspect the program before retrying": "Il salvataggio non è confermato. Aggiorna e controlla il programma prima di riprovare.",
      "Operation failed; refresh before retrying": "Operazione non riuscita. Aggiorna prima di riprovare."
    };
    return known[message] || message;
  }
  _setDraft(program, fresh = false) {
    this._draft = { number: program.program_number, name: program.name || "", days: {} };
    for (const day of DAYS) this._draft.days[day] = (program.days[day] || []).map(({ time, preset }) => ({ time, preset }));
    this._revision = fresh ? null : program.sha256; this._original = clone(program);
    this._baseline = fresh ? null : JSON.stringify(this._draft);
    if (!fresh) this._profiles[program.program_number] = clone(program);
    this._editing = fresh;
  }
  async _load(refresh = false) {
    if (refresh && !this._canLeave()) return;
    this._attempted = true;
    await this._run(async () => {
      this._catalog = await this._api("list", { refresh });
      this._profiles = {};
      if (refresh) this._message = this._t("loaded");
      const number = this._draft?.number ?? this._catalog.active_program;
      const record = this._catalog.programs.find(p => p.number === number && !p.error);
      if (record) {
        const result = await this._api("get", { number: record.number });
        this._catalog = result.catalog; this._setDraft(result.program);
      } else if (refresh) { this._draft = null; this._baseline = null; }
      await this._fetchActive();
    });
  }
  async _fetchActive() {
    const number = this._catalog?.active_program;
    if (number == null || this._profiles[number] || !this._catalog.programs.some(p => p.number === number && p.valid && !p.error)) return;
    const data = await this._api("get", { number }); this._profiles[number] = clone(data.program); this._catalog = data.catalog;
  }
  _ensureActive() { const number = this._catalog?.active_program; if (!this._profiles[number] && this._catalog.programs.some(p => p.number === number && p.valid && !p.error)) this._run(() => this._fetchActive()); }
  async _open(number) {
    if (!this._canLeave()) return;
    await this._run(async () => { const data = await this._api("get", { number }); this._catalog = data.catalog; this._setDraft(data.program); });
  }
  _new(duplicate = false) {
    if (!this._admin() || !this._canLeave()) return;
    const number = this._catalog?.free_slots?.[0];
    if (number == null) { this._error = this._t("noSpace"); this._render(); return; }
    const days = duplicate && this._draft ? clone(this._draft.days) : Object.fromEntries(DAYS.map(d => [d, [{ time: "00:00", preset: "PROTECTION" }]]));
    const name = duplicate ? `${this._t("copyName")} ${this._draft.name}`.slice(0, 40) : this._t("newName");
    this._view = "programs"; this._setDraft({ program_number: number, name, days }, true); this._error = ""; this._message = ""; this._render();
  }
  _validate(draft = this._draft) {
    if (!draft || !draft.name.trim() || draft.name.trim().length > 40 || Object.keys(draft.days).length !== 7) return false;
    return DAYS.every(day => {
      const slots = draft.days[day];
      return Array.isArray(slots) && slots.length > 0 && slots.length <= 8 && slots[0].time === "00:00" &&
        slots.every((s, i) => /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(s.time) && PRESETS.includes(s.preset) && (!i || s.time > slots[i - 1].time));
    });
  }
  async _save() {
    if (!this._validate()) { this._error = this._t("invalid"); this._render(); return; }
    await this._run(async () => {
      const data = await this._api("save", { ...clone(this._draft), number: this._draft.number, revision: this._revision });
      this._catalog = data.catalog; this._setDraft(data.program); this._message = this._t("saved");
    });
  }
  async _activate(number) {
    if (!this._admin() || number == null) return;
    await this._run(async () => { this._catalog = await this._api("activate", { number }); await this._fetchActive(); this._message = this._t("activated"); });
  }
  async _delete() {
    if (!this._revision || !window.confirm(this._t("removeAsk"))) return;
    await this._run(async () => {
      this._catalog = await this._api("delete", { number: this._draft.number, revision: this._revision });
      this._draft = null; this._baseline = null; this._message = this._t("deleted");
    });
  }
  _copyDay() {
    const target = this.shadowRoot.querySelector("[data-field=copy-target]").value;
    const targets = target === "all" ? DAYS : target === "weekdays" ? DAYS.slice(0, 5) : target === "weekend" ? DAYS.slice(5) : [target];
    const slots = clone(this._draft.days[this._day]);
    for (const day of targets) this._draft.days[day] = clone(slots);
    this._message = this._t("copied"); this._render();
  }
  _export() {
    const blob = new Blob([JSON.stringify({ format: "bticino-weekly-program-v1", ...this._draft }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = `bticino-program-${this._draft.number}.json`; link.click(); URL.revokeObjectURL(url);
  }
  async _import(file) {
    if (!file || !this._canLeave()) return;
    try {
      if (file.size > 262144) throw new Error();
      const data = JSON.parse(await file.text());
      if (data.format !== "bticino-weekly-program-v1" || typeof data.name !== "string" || !this._validate(data)) throw new Error();
      const number = this._catalog.free_slots[0]; if (number == null) { this._error = this._t("noSpace"); this._render(); return; }
      this._setDraft({ program_number: number, name: data.name, days: data.days }, true); this._error = ""; this._render();
    } catch { this._error = this._t("invalidImport"); this._render(); }
  }
  _input(event) {
    const el = event.target;
    if (!this._draft || this._readOnly() || this._busy) return;
    if (el.dataset.field === "name") this._draft.name = el.value;
    if (el.dataset.field === "time") this._draft.days[this._day][Number(el.dataset.index)].time = el.value;
    if (el.dataset.field === "preset") this._draft.days[this._day][Number(el.dataset.index)].preset = el.value;
    this._updateDirty();
    const preview = this.shadowRoot.querySelector(".week-preview"); if (preview) preview.innerHTML = this._weekMarkup();
    this.shadowRoot.querySelectorAll(".slot-end").forEach((node, i) => { node.textContent = this._draft.days[this._day][i + 1]?.time || "24:00"; });
  }
  _change(event) {
    const el = event.target;
    if (el.dataset.field === "active" && el.value !== "") this._activate(Number(el.value));
    if (el.dataset.field === "number" && !this._revision) { this._draft.number = Number(el.value); this._updateDirty(); }
    if (el.dataset.field === "import") this._import(el.files[0]);
    if (["time", "preset"].includes(el.dataset.field)) this._input(event);
  }
  _click(event) {
    const el = event.target.closest("[data-action]"); if (!el || this._busy) return;
    const action = el.dataset.action;
    if (el.disabled) return;
    if (action === "refresh") this._load(true);
    else if (action === "view") { this._view = el.dataset.view; this._render(); if (this._view === "today") this._ensureActive(); }
    else if (action === "edit-day") { this._editing = !this._editing; this._render(); }
    else if (action === "inspect-period") { this._inspected = { number: this._catalog.active_program, day: this._clock().day, index: Number(el.dataset.index) }; this._render(); this.shadowRoot.querySelector(`.day-segment[data-index="${this._inspected.index}"]`)?.focus({ preventScroll: true }); }
    else if (action === "open") this._open(Number(el.dataset.number));
    else if (action === "new") this._new();
    else if (action === "duplicate") this._new(true);
    else if (action === "save") this._save();
    else if (action === "activate") this._activate(this._draft.number);
    else if (action === "delete") this._delete();
    else if (action === "day") { this._day = el.dataset.day; this._render(); }
    else if (action === "discard") { if (this._canLeave()) { if (this._revision) this._setDraft(this._original); else this._draft = null; this._render(); } }
    else if (action === "remove-slot") { this._draft.days[this._day].splice(Number(el.dataset.index), 1); this._render(); }
    else if (action === "add-slot") {
      const slots = this._draft.days[this._day]; const last = minutes(slots[slots.length - 1].time);
      const next = Math.min(1439, last + 60); if (next <= last) return;
      slots.push({ time: `${String(Math.floor(next / 60)).padStart(2, "0")}:${String(next % 60).padStart(2, "0")}`, preset: "DAY" }); this._render();
    } else if (action === "copy") this._copyDay();
    else if (action === "export") this._export();
    else if (action === "import") this.shadowRoot.querySelector("input[type=file]").click();
  }
  _presetLabel(preset) {
    const label = this._t(({ DAY: "day", NIGHT: "night", AWAY: "away", PROTECTION: "protection" })[preset] || "protection");
    const temps = this._catalog?.temperatures; const functionKey = this._catalog?.function === "COOLING" ? "cooling" : "heating";
    const value = temps?.[functionKey]?.[preset];
    return value == null ? label : `${label} · ${Number(value).toLocaleString(this._hass?.language)} °${temps.temperature_format === "FAHRENHEIT" ? "F" : "C"}`;
  }
  _weekMarkup() {
    if (!this._draft) return "";
    return DAYS.map((day, i) => {
      const slots = this._draft.days[day];
      const segments = slots.map((slot, index) => {
        const start = minutes(slot.time), end = index + 1 < slots.length ? minutes(slots[index + 1].time) : 1440;
        const width = Math.max(0, (end - start) / 14.4);
        const label = `${slot.time}–${index + 1 < slots.length ? slots[index + 1].time : "24:00"}: ${this._presetLabel(slot.preset)}`;
        return `<span class="segment ${PRESETS.includes(slot.preset) ? slot.preset.toLowerCase() : "protection"}" style="width:${Number.isFinite(width) ? width : 0}%" title="${esc(label)}" aria-label="${esc(label)}"></span>`;
      }).join("");
      return `<button class="week-row ${this._day === day ? "selected" : ""}" data-action="day" data-day="${day}" aria-label="${esc(this._t("weekdaysLong")[i])}"><span>${esc(this._t("weekdaysShort")[i])}</span><span class="timeline">${segments}</span></button>`;
    }).join("") + '<div class="axis"><span></span><div><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div></div>';
  }
  _updateDirty() {
    const button = this.shadowRoot.querySelector("[data-action=save]");
    if (button) button.disabled = this._busy || this._readOnly() || !this._dirty();
    const activate = this.shadowRoot.querySelector("[data-action=activate]");
    if (activate) activate.disabled = this._busy || this._readOnly() || this._dirty();
    const discard = this.shadowRoot.querySelector("[data-action=discard]");
    if (discard) discard.disabled = this._busy || !this._dirty();
    const flag = this.shadowRoot.querySelector(".dirty"); if (flag) flag.hidden = !this._dirty();
    const picker = this.shadowRoot.querySelector("[data-field=active]"); if (picker) picker.disabled = this._busy || !this._admin() || this._dirty();
  }
  _clock() {
    const zone = this._hass?.config?.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone;
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: zone, weekday: "long", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date()).map(p => [p.type, p.value]));
    return { day: parts.weekday.toLowerCase(), time: `${parts.hour}:${parts.minute}`, minute: Number(parts.hour) * 60 + Number(parts.minute), zone };
  }
  _periods(slots, current = -1) {
    return `<ol class="periods">${slots.map((slot, i) => `<li class="period ${i === current ? "current" : ""}"><span class="period-time">${esc(slot.time)} <span>–</span> ${esc(slots[i + 1]?.time || "24:00")}</span><strong class="${slot.preset.toLowerCase()}"><i></i>${esc(this._presetLabel(slot.preset))}</strong>${i === current ? `<span class="now-badge">${esc(this._t("now"))}</span>` : ""}</li>`).join("")}</ol>`;
  }
  _dayTimeline(slots, current, clock, compact = false) {
    const inspected = this._inspected;
    const selected = inspected?.number === this._catalog.active_program && inspected.day === clock.day && slots[inspected.index] ? inspected.index : Math.max(0, current);
    const slot = slots[selected], end = slots[selected + 1]?.time || "24:00";
    return `<div class="day-timeline ${compact ? "compact-timeline" : ""}" aria-label="${esc(this._t("daily"))}">
      <div class="day-track">${slots.map((s, i) => {
        const width = ((i + 1 < slots.length ? minutes(slots[i + 1].time) : 1440) - minutes(s.time)) / 14.4;
        const label = `${s.time}–${slots[i + 1]?.time || "24:00"} · ${this._presetLabel(s.preset)}`;
        const value = this._catalog.temperatures?.[this._catalog.function === "COOLING" ? "cooling" : "heating"]?.[s.preset];
        const shortLabel = value == null ? this._presetLabel(s.preset) : `${Number(value).toLocaleString(this._hass?.language)}°`;
        return `<button class="day-segment ${s.preset.toLowerCase()} ${i === current ? "current" : ""}" data-action="inspect-period" data-index="${i}" style="width:${width}%" aria-label="${esc(label)}" aria-pressed="${selected === i}" title="${esc(label)}"><span>${width >= 10 ? esc(shortLabel) : ""}</span></button>`;
      }).join("")}${current >= 0 ? `<div class="time-cursor" style="left:${clock.minute / 14.4}%"><span style="transform:translateX(${clock.minute < 90 ? "0" : clock.minute > 1350 ? "-100%" : "-50%"})">${esc(clock.time)}</span></div>` : ""}</div>
      <div class="day-axis">${[0, 6, 12, 18, 24].map(h => `<span>${String(h).padStart(2, "0")}:00</span>`).join("")}</div>
      ${compact ? "" : `<div class="timeline-detail" role="status"><span>${esc(slot.time)} – ${esc(end)}</span><strong>${esc(this._presetLabel(slot.preset))}</strong></div>
      <div class="legend">${[...new Set(slots.map(s => s.preset))].map(p => `<span><i class="${p.toLowerCase()}"></i>${esc(this._presetLabel(p))}</span>`).join("")}</div>
      <details class="period-list"><summary>${this._hass?.language?.startsWith("it") ? "Elenco delle fasce" : "List of periods"}</summary>${this._periods(slots, current)}</details>`}
    </div>`;
  }
  _compactTodayMarkup() {
    const clock = this._clock(), catalog = this._catalog, profile = this._profiles[catalog?.active_program];
    const slots = profile?.days?.[clock.day] || [];
    const running = catalog?.connected && catalog.mode === "AUTOMATIC" && this._hass?.states?.[this._config.entity]?.state !== "off";
    let current = -1;
    if (running) slots.forEach((slot, i) => { if (minutes(slot.time) <= clock.minute) current = i; });
    const warning = this._error || (!catalog?.connected ? this._t("offline") : !running ? this._t("paused") : "");
    const label = `${profile?.name || this._t("today")} · ${this._t("weekdaysLong")[DAYS.indexOf(clock.day)]}${warning ? ` · ${warning}` : ""}`;
    return `<style>${STYLE}${SIMPLE_STYLE}</style><ha-card class="compact-card" role="group" aria-label="${esc(label)}">
      ${slots.length ? this._dayTimeline(slots, current, clock, true) : `<p class="empty" role="status">${esc(this._busy ? this._t("loading") : warning || this._t("noActive"))}</p>`}
      ${warning && slots.length ? `<span class="strip-status" role="img" aria-label="${esc(warning)}" title="${esc(warning)}">!</span>` : ""}</ha-card>`;
  }
  _todayMarkup() {
    const catalog = this._catalog, clock = this._clock(), state = this._hass?.states?.[this._config.entity];
    const profile = this._profiles[catalog?.active_program];
    const running = catalog?.connected && catalog.mode === "AUTOMATIC" && state?.state !== "off";
    const slots = profile?.days?.[clock.day] || [];
    let current = -1;
    if (running) slots.forEach((slot, i) => { if (minutes(slot.time) <= clock.minute) current = i; });
    const next = current >= 0 ? slots[current + 1] : null;
    const tomorrow = profile?.days?.[DAYS[(DAYS.indexOf(clock.day) + 1) % 7]]?.[0];
    const target = catalog?.connected ? state?.attributes?.temperature : null;
    return `<section class="today-panel" aria-label="${esc(this._t("today"))}">
      <div class="today-heading"><div><span class="eyebrow">${esc(this._t("today"))} · ${esc(this._t("weekdaysLong")[DAYS.indexOf(clock.day)])}</span><h3>${esc(profile?.name || this._t("noActive"))}</h3></div><time>${esc(clock.time)}</time></div>
      ${!catalog?.connected ? `<p class="notice" role="status">${esc(this._t("offline"))}</p>` : !running ? `<p class="notice" role="status">${esc(this._t("paused"))}</p>` : ""}
      <div class="today-summary"><div class="current-period"><span class="eyebrow">${esc(running && current >= 0 ? this._t("now") : this._t("actual"))}</span><strong>${esc(running && current >= 0 ? this._presetLabel(slots[current].preset) : target == null ? "—" : `${target} °${this._hass?.config?.unit_system?.temperature || "C"}`)}</strong>${running && current >= 0 ? `<span>${esc(this._t("until"))} ${esc(slots[current + 1]?.time || "24:00")}</span>` : ""}</div>
      ${running && current >= 0 && (next || tomorrow) ? `<div class="next-period"><span class="eyebrow">${esc(this._t("next"))}</span><strong>${esc(this._presetLabel((next || tomorrow).preset))}</strong><span>${next ? esc(next.time) : `${esc(this._t("tomorrow"))} ${esc(tomorrow.time)}`}</span></div>` : ""}</div>
      ${running && target != null ? `<p class="actual-target">${esc(this._t("actual"))}: <strong>${esc(target)} °${esc(this._hass?.config?.unit_system?.temperature || "C")}</strong></p>` : ""}
      <h4>${esc(running ? this._t("daily") : this._t("scheduled"))}</h4>
      ${slots.length ? this._dayTimeline(slots, current, clock) : `<p class="empty">${esc(this._t("empty"))}</p>`}
      <p class="footnote">${esc(this._t("timezone"))}: ${esc(clock.zone)}. ${esc(this._t("clockNote"))}</p>
      ${catalog?.temperature_warning ? `<p class="footnote">${esc(this._t("uncertain"))}</p>` : ""}
    </section>`;
  }
  _editorMarkup(disabled) {
    const draft = this._draft, catalog = this._catalog, admin = this._admin(), readOnly = this._readOnly(), noSlots = !catalog?.free_slots?.length;
    const active = catalog?.mode === "AUTOMATIC" ? catalog.active_program : null;
    if (!draft) return `<p class="empty editor-empty">${esc(this._t("selectFirst"))}</p>`;
    const slots = draft.days[this._day];
    return `<div class="program-heading">${this._editing ? `<label class="name-label">${esc(this._t("name"))}<input maxlength="40" data-field="name" value="${esc(draft.name)}" ${disabled} ${readOnly ? "disabled" : ""}></label>` : `<div><span class="eyebrow">${esc(this._t("readProgram"))}</span><h3>${esc(draft.name)}</h3></div>`}
      <button data-action="edit-day" ${disabled} ${readOnly ? "disabled" : ""}>${esc(this._t(this._editing ? "done" : "editDay"))}</button></div>
      ${draft.number === 0 ? `<p class="notice">${esc(this._t("readOnly"))}</p>` : ""}
      ${draft.number === active && this._editing && !readOnly ? `<p class="notice">${esc(this._t("activeEdit"))}</p>` : ""}
      <section aria-label="${esc(this._t("week"))}">${this._editing ? `<div class="day-tabs">${DAYS.map((day, i) => `<button data-action="day" data-day="${day}" aria-pressed="${this._day === day}">${esc(this._t("weekdaysShort")[i])}</button>`).join("")}</div>` : `<p class="footnote">${esc(this._t("chooseDay"))}</p><div class="week-preview">${this._weekMarkup()}</div>`}</section>
      <section class="day-editor"><h3>${esc(this._t("weekdaysLong")[DAYS.indexOf(this._day)])}</h3>
      ${!this._editing ? this._periods(slots) : `<div class="slot-head"><span>${esc(this._t("from"))}</span><span>${esc(this._t("to"))}</span><span>${esc(this._t("level"))}</span><span></span></div>
      ${slots.map((slot, i) => `<div class="slot-row"><input type="time" step="60" data-field="time" data-index="${i}" aria-label="${esc(this._t("hour"))} ${i + 1}" value="${esc(slot.time)}" ${disabled} ${readOnly || i === 0 ? "disabled" : ""}><span class="slot-end">${esc(slots[i + 1]?.time || "24:00")}</span><select data-field="preset" data-index="${i}" aria-label="${esc(this._t("level"))} ${i + 1}" ${disabled} ${readOnly ? "disabled" : ""}>${PRESETS.map(p => `<option value="${p}" ${p === slot.preset ? "selected" : ""}>${esc(this._presetLabel(p))}</option>`).join("")}</select><button data-action="remove-slot" data-index="${i}" title="${esc(this._t("deleteSlot"))}" aria-label="${esc(this._t("deleteSlot"))} ${i + 1}" ${disabled} ${readOnly || i === 0 ? "disabled" : ""}>×</button></div>`).join("")}
      <button data-action="add-slot" ${disabled} ${readOnly || slots.length >= 8 ? "disabled" : ""}>＋ ${esc(this._t("add"))}</button>
      <details class="copy-options"><summary>${esc(this._t("copy"))}</summary><div class="copy-row"><label>${esc(this._t("copy"))}<select data-field="copy-target" ${disabled} ${readOnly ? "disabled" : ""}><option value="all">${esc(this._t("all"))}</option><option value="weekdays">${esc(this._t("weekdays"))}</option><option value="weekend">${esc(this._t("weekend"))}</option>${DAYS.map((d, i) => `<option value="${d}">${esc(this._t("weekdaysLong")[i])}</option>`).join("")}</select></label><button data-action="copy" ${disabled} ${readOnly ? "disabled" : ""}>${esc(this._t("applyCopy"))}</button></div></details>`}</section>
      <div class="save-row"><div><span class="dirty" ${this._dirty() ? "" : "hidden"}>${esc(this._t("unsaved"))}</span><button data-action="discard" ${disabled} ${!this._dirty() ? "disabled" : ""}>${esc(this._t("discard"))}</button></div><button class="primary" data-action="save" ${disabled} ${readOnly || !this._dirty() ? "disabled" : ""}>${esc(this._t("save"))}</button></div>
      <details class="more-options"><summary>${esc(this._t("more"))}</summary><div class="program-tools"><button data-action="duplicate" ${disabled} ${!admin || noSlots ? "disabled" : ""}>${esc(this._t("duplicate"))}</button><button data-action="export" ${disabled}>${esc(this._t("export"))}</button><button data-action="import" ${disabled} ${!admin || noSlots ? "disabled" : ""}>${esc(this._t("import"))}</button>${this._revision && draft.number > 0 ? `<button data-action="activate" ${disabled} ${!admin || this._dirty() ? "disabled" : ""}>${esc(this._t("activate"))}</button>` : ""}</div>
      ${!this._revision ? `<label class="number-label">${esc(this._t("slot"))}<select data-field="number" ${disabled} ${readOnly ? "disabled" : ""}>${catalog.free_slots.map(n => `<option value="${n}" ${n === draft.number ? "selected" : ""}>${n}</option>`).join("")}</select></label>` : ""}
      <div class="legend">${PRESETS.map(p => `<span><i class="${p.toLowerCase()}"></i>${esc(this._presetLabel(p))}</span>`).join("")}</div><p class="footnote">${esc(this._t("presetNote"))} ${esc(!catalog.temperatures ? this._t("missingTemps") : catalog.temperature_warning ? this._t("uncertain") : "")}</p>
      ${this._revision && draft.number > 0 ? `<button class="delete" data-action="delete" ${disabled} ${readOnly || draft.number === catalog.active_program ? "disabled" : ""}>${esc(this._t("remove"))}</button>` : ""}</details>`;
  }
  _render() {
    if (!this._config) return;
    if (this._todayOnly && !this._config.show_details) { this.shadowRoot.innerHTML = this._compactTodayMarkup(); return; }
    const catalog = this._catalog, draft = this._draft, disabled = this._busy ? "disabled" : "";
    const records = catalog?.programs || [], active = catalog?.mode === "AUTOMATIC" ? catalog.active_program : null;
    const noSlots = !catalog?.free_slots?.length, admin = this._admin(), todayOnly = this._todayOnly;
    const options = records.filter(p => p.number > 0 && p.valid && !p.error).map(p => `<option value="${p.number}" ${p.number === active ? "selected" : ""}>${esc(p.name)} · #${p.number}</option>`).join("");
    this.shadowRoot.innerHTML = `<style>${STYLE}${SIMPLE_STYLE}</style><ha-card>
      <header><div><h2>${esc(this._config.title || this._t(todayOnly ? "todayTitle" : "title"))}</h2><div class="subtitle">${esc(this._hass?.states?.[this._config.entity]?.attributes?.friendly_name || "")}</div></div><button data-action="refresh" ${disabled}>↻ ${esc(this._t("refresh"))}</button></header>
      ${!todayOnly ? `<div class="view-tabs" role="tablist">${["programs", "today"].map(view => `<button role="tab" aria-selected="${this._view === view}" data-action="view" data-view="${view}">${esc(this._t(view))}</button>`).join("")}</div>` : ""}
      ${this._error ? `<div class="notice error" role="alert">${esc(this._error)}</div>` : ""}${this._message ? `<div class="notice success" role="status">${esc(this._message)}</div>` : ""}${this._busy ? `<div class="loading" role="status">${esc(this._t("loading"))}</div>` : ""}
      ${this._view === "today" ? this._todayMarkup() : `<div class="active-picker"><label>${esc(this._t("active"))}<select data-field="active" ${disabled} ${!admin || this._dirty() ? "disabled" : ""}><option value="" ${active == null ? "selected" : ""}>${esc(this._t("choose"))}</option>${options}</select></label><span class="mode">${esc(!catalog?.connected ? this._t("offline") : catalog?.mode === "AUTOMATIC" ? this._t("automatic") : this._t("manual"))}</span></div>
      <div class="workspace"><aside><div class="list-actions"><button data-action="new" ${disabled} ${!admin || noSlots ? "disabled" : ""}>＋ ${esc(this._t("create"))}</button></div><nav aria-label="${esc(this._t("readProgram"))}">${records.map(p => `<button class="program ${draft?.number === p.number && this._revision ? "selected" : ""}" data-action="open" data-number="${p.number}" ${disabled} ${p.error ? "disabled" : ""}><span class="program-name">${esc(p.name)}</span><span class="program-meta">${p.number === 0 ? esc(this._t("default")) : `#${p.number}`} ${p.number === active ? `· ${esc(this._t("active"))}` : ""}</span></button>`).join("") || `<p class="empty">${esc(this._t("empty"))}</p>`}</nav></aside><main>${this._editorMarkup(disabled)}</main></div>`}
      ${!todayOnly ? `<input hidden type="file" accept=".json,application/json" data-field="import"><footer>${esc(this._t("note"))}${!admin ? `<br>${esc(this._t("admin"))}` : ""}</footer>` : ""}</ha-card>`;
  }
}

const STYLE = `
  :host{display:block;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit)}*{box-sizing:border-box}
  ha-card{display:block;background:var(--ha-card-background,var(--card-background-color));border-radius:var(--ha-card-border-radius,12px);overflow:hidden}
  header{display:flex;justify-content:space-between;align-items:center;padding:22px 22px 14px;gap:16px}h2{margin:0;font-size:21px;font-weight:550;letter-spacing:-.3px}.subtitle{font-size:12px;color:var(--secondary-text-color);margin-top:5px}
  button,input,select{font:inherit;color:var(--primary-text-color)}button{cursor:pointer;border:1px solid var(--divider-color);background:transparent;border-radius:8px;padding:9px 12px;font-size:13px}button:hover:not(:disabled){background:var(--secondary-background-color)}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}button:disabled{opacity:.45;cursor:default}input,select{min-width:0;border:1px solid var(--divider-color);background:var(--ha-card-background,var(--card-background-color));border-radius:7px;padding:10px;font-size:14px}input:disabled,select:disabled{opacity:.65}label{display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--secondary-text-color)}
  .active-picker{display:flex;align-items:flex-end;gap:16px;padding:0 22px 18px}.active-picker label{flex:1}.mode{font-size:12px;color:var(--secondary-text-color);padding-bottom:11px}
  .workspace{display:grid;grid-template-columns:180px minmax(0,1fr);border-top:1px solid var(--divider-color)}aside{padding:14px 10px;background:var(--secondary-background-color)}.list-actions{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px}.list-actions button{flex:1}nav{display:flex;flex-direction:column;gap:7px}.program{text-align:left;border-color:transparent;padding:12px 9px}.program.selected{background:var(--ha-card-background,var(--card-background-color));box-shadow:0 1px 4px var(--divider-color)}.program-name{display:block;font-size:13px;font-weight:550;overflow-wrap:anywhere}.program-meta{display:block;font-size:11px;color:var(--secondary-text-color);margin-top:5px}main{padding:18px;min-width:0}.program-heading{display:flex;gap:10px}.name-label{flex:1}.number-label{width:65px}.program-tools{display:flex;gap:7px;margin:12px 0 18px;flex-wrap:wrap}.program-tools button{padding:7px 10px;font-size:12px}
  .legend{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0;font-size:11px;color:var(--secondary-text-color)}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:9px;height:9px;border-radius:3px;display:inline-block;background:var(--tone)}.day{--tone:var(--primary-color)}.night{--tone:var(--info-color,var(--primary-color))}.away{--tone:var(--warning-color)}.protection{--tone:var(--secondary-text-color)}
  .week-row{display:grid;grid-template-columns:40px minmax(0,1fr);align-items:center;gap:8px;width:100%;padding:4px 0;border:0;border-radius:0;background:none;text-align:left;font-size:11px;color:var(--secondary-text-color)}.week-row.selected>span:first-child{color:var(--primary-color);font-weight:700}.timeline{height:26px;display:flex;border-radius:5px;overflow:hidden;background:var(--secondary-background-color);position:relative}.segment{height:100%;background:color-mix(in srgb,var(--tone) 50%,transparent);display:block;flex-shrink:0}.week-row:hover .timeline{filter:brightness(.97)}.axis{display:grid;grid-template-columns:48px 1fr;margin:4px 0 16px;font-size:10px;color:var(--secondary-text-color)}.axis>div{display:flex;justify-content:space-between}
  .day-editor{border-top:1px solid var(--divider-color);padding-top:14px}h3{font-size:15px;font-weight:550;margin:0 0 12px}.slot-row,.slot-head{display:grid;grid-template-columns:95px minmax(0,1fr) 32px;gap:8px;margin:7px 0;align-items:center}.slot-head{font-size:11px;color:var(--secondary-text-color);margin-bottom:5px}.slot-row input,.slot-row select{width:100%;padding:8px;font-size:13px}.slot-row button{padding:5px;font-size:20px;border:0}.copy-row{display:flex;align-items:flex-end;gap:8px;margin:16px 0 5px}.copy-row label{flex:1}.copy-row select{font-size:12px}.copy-row button{height:37px}.footnote{font-size:11px;color:var(--secondary-text-color);line-height:1.55;margin:14px 0}.save-row{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;border-top:1px solid var(--divider-color);padding-top:14px}.save-row>div{display:flex;flex-direction:column;gap:7px;align-items:flex-start}.dirty{font-size:11px;color:var(--warning-color)}.primary{background:var(--primary-color);color:var(--text-primary-color);border-color:var(--primary-color)}.primary:hover:not(:disabled){background:var(--primary-color);filter:brightness(.95)}.delete{color:var(--error-color);border:0;margin-top:12px;padding-left:0;font-size:12px}.notice{margin:8px 0 12px;padding:10px 12px;border-radius:7px;background:var(--secondary-background-color);font-size:12px;line-height:1.5}.error{margin:0 22px 12px;color:var(--error-color)}.success{margin:0 22px 12px;color:var(--success-color,var(--primary-color))}.loading{padding:8px 22px;color:var(--secondary-text-color);font-size:12px}.empty{font-size:12px;color:var(--secondary-text-color);line-height:1.6}.editor-empty{padding:35px 12px;text-align:center}footer{border-top:1px solid var(--divider-color);padding:14px 22px;font-size:11px;line-height:1.5;color:var(--secondary-text-color)}[hidden]{display:none!important}
  @media(max-width:600px){.workspace{grid-template-columns:1fr}aside{padding:10px}nav{flex-direction:row;overflow:auto}.program{min-width:135px;max-width:190px}.list-actions{justify-content:flex-start;margin-bottom:8px}.list-actions button{flex:0 1 auto}.program-meta{font-size:10px}header{padding:16px}.active-picker{padding:0 16px 14px;gap:8px}h2{font-size:19px}main{padding:15px}.save-row{align-items:stretch}.save-row button{font-size:12px}.mode{max-width:90px}.slot-row,.slot-head{grid-template-columns:90px minmax(0,1fr) 28px}}
`;

const SIMPLE_STYLE = `
  .compact-card{position:relative;padding:8px 12px}.compact-timeline.day-timeline{margin-top:23px}.compact-timeline .day-track{height:34px}.compact-timeline .day-axis{margin:9px 0 2px;font-size:9px}.compact-timeline .day-segment{font-size:11px}.strip-status{position:absolute;right:8px;top:5px;color:var(--warning-color);font-size:12px;font-weight:700}
  .day-track>.day-segment:only-of-type{border-radius:9px}
  .day-timeline{margin-top:34px}.day-track{position:relative;display:flex;height:58px;border-radius:9px;background:var(--secondary-background-color)}.day-segment{position:relative;display:flex;align-items:center;justify-content:center;flex-shrink:0;min-width:0;padding:0;border:0;border-right:1px solid var(--ha-card-background,var(--card-background-color));border-radius:0;background:color-mix(in srgb,var(--tone) 48%,var(--ha-card-background,var(--card-background-color)));overflow:hidden;font-size:12px;font-weight:600}.day-segment:first-child{border-radius:9px 0 0 9px}.day-segment:last-of-type{border-radius:0 9px 9px 0}.day-segment:hover:not(:disabled){background:color-mix(in srgb,var(--tone) 65%,var(--ha-card-background,var(--card-background-color)))}.day-segment>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 6px}.day-segment[aria-pressed=true]{box-shadow:inset 0 0 0 2px var(--primary-text-color)}.time-cursor{position:absolute;top:-9px;bottom:-5px;width:2px;background:var(--primary-text-color);pointer-events:none;transform:translateX(-1px)}.time-cursor>span{position:absolute;bottom:calc(100% + 4px);left:0;transform:translateX(-50%);background:var(--primary-text-color);color:var(--card-background-color);border-radius:4px;padding:3px 5px;font-size:10px;white-space:nowrap}.time-cursor>span:after{content:"";position:absolute;left:calc(50% - 3px);top:100%;border:3px solid transparent;border-top-color:var(--primary-text-color)}.day-axis{display:flex;justify-content:space-between;margin:12px 0 16px;font-size:10px;font-variant-numeric:tabular-nums;color:var(--secondary-text-color)}.timeline-detail{display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap;border-radius:8px;background:var(--secondary-background-color);padding:12px;font-size:13px}.timeline-detail>span{font-variant-numeric:tabular-nums;color:var(--secondary-text-color)}.timeline-detail strong{font-weight:550}.day-timeline .legend{margin:14px 0 8px}
  h3{margin:4px 0 0;font-size:18px;overflow-wrap:anywhere}h4{font-size:14px;margin:24px 0 10px}
  .view-tabs{display:flex;gap:5px;padding:0 22px 18px}.view-tabs button{border:0;border-radius:24px;padding:10px 20px}.view-tabs button[aria-selected=true]{background:var(--primary-color);color:var(--text-primary-color)}
  .day-tabs{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;margin:20px 0 16px}.day-tabs button{padding:10px 0;font-size:12px}.day-tabs button[aria-pressed=true]{background:var(--primary-color);color:var(--text-primary-color);border-color:var(--primary-color)}
  .program-heading{justify-content:space-between;align-items:center;gap:12px}.program-heading>div,.name-label{min-width:0}.name-label input{width:100%}.program-heading>button{flex-shrink:0}.eyebrow{text-transform:uppercase;letter-spacing:.07em;font-size:10px;color:var(--secondary-text-color)}
  .periods{list-style:none;padding:0;margin:12px 0}.period{display:flex;align-items:center;gap:12px;padding:13px 10px;border-bottom:1px solid var(--divider-color);flex-wrap:wrap;font-size:13px}.period-time{font-variant-numeric:tabular-nums;color:var(--secondary-text-color);white-space:nowrap}.period-time>span{opacity:.5;margin:0 2px}.period strong{display:flex;align-items:center;gap:8px;font-weight:550}.period i{display:block;width:9px;height:9px;border-radius:50%;background:var(--tone)}.period.current{border-radius:10px;border:1px solid var(--primary-color);background:color-mix(in srgb,var(--primary-color) 8%,transparent)}.now-badge{font-size:10px;color:var(--primary-color);margin-left:auto;font-weight:600}
  .slot-row,.slot-head{grid-template-columns:90px 48px minmax(0,1fr) 28px}.slot-end{font-size:12px;color:var(--secondary-text-color);font-variant-numeric:tabular-nums}.copy-options{margin:15px 0}.more-options{margin-top:18px;border-top:1px solid var(--divider-color);padding-top:14px}summary{cursor:pointer;font-size:12px;color:var(--secondary-text-color);padding:8px 0}details[open]>summary{color:var(--primary-text-color)}.program-tools{margin-top:12px}.save-row{margin-top:16px;position:sticky;bottom:0;background:var(--ha-card-background,var(--card-background-color));padding-bottom:12px;z-index:1}.save-row:not(:has(.dirty:not([hidden]))){display:none}.day-editor{padding-bottom:0}
  .today-panel{padding:6px 22px 18px}.today-heading{display:flex;align-items:center;justify-content:space-between;gap:14px}.today-heading h3{font-size:22px;margin-top:6px}.today-heading time{font-size:24px;font-variant-numeric:tabular-nums;letter-spacing:-1px;color:var(--secondary-text-color)}.today-summary{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px}.today-summary>div{display:flex;flex-direction:column;gap:9px;border-radius:12px;padding:18px;background:var(--secondary-background-color)}.today-summary strong{font-size:21px;font-weight:550;overflow-wrap:anywhere}.today-summary>div>span:last-child{font-size:12px;color:var(--secondary-text-color)}.current-period{border-left:3px solid var(--primary-color)}.actual-target{font-size:12px;color:var(--secondary-text-color)}
  @media(max-width:600px){.today-panel{padding:5px 16px 16px}.view-tabs{padding-left:16px}.program-heading{align-items:flex-start}.program-heading>button{font-size:12px;padding:8px}.slot-row,.slot-head{grid-template-columns:78px 40px minmax(0,1fr) 24px;gap:5px}.slot-row select{padding:8px 3px;font-size:12px}.slot-row input{padding:8px 3px}.today-summary{gap:8px}.today-summary>div{padding:13px}.today-summary strong{font-size:18px}.today-heading h3{font-size:19px}.period{gap:8px;padding:12px 6px}.period strong{font-size:12px}.now-badge{font-size:9px}}
`;

class BticinoTodayCard extends BticinoProgramsCard {
  constructor() { super(); this._todayOnly = true; this._view = "today"; }
  getCardSize() { return this._config?.show_details ? 5 : 2; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: this._config?.show_details ? 6 : 2, min_rows: 2 }; }
}

class BticinoProgramsCardEditor extends HTMLElement {
  setConfig(config) { this._config = { ...config }; this._render(); }
  set hass(hass) { const changed = hass.language !== this._hass?.language; this._hass = hass; if (changed && this._config) { this._render(); return; } const picker = this.querySelector("ha-entity-picker"); if (picker) picker.hass = hass; }
  _render() {
    this.innerHTML = '<div style="display:grid;gap:16px;padding:12px 0"><ha-entity-picker></ha-entity-picker><label><span></span><input style="display:block;width:100%;padding:10px;margin-top:6px"></label></div>';
    const t = LABELS[this._hass?.language?.startsWith("it") ? "it" : "en"];
    const picker = this.querySelector("ha-entity-picker"); picker.hass = this._hass; picker.includeDomains = ["climate"]; picker.label = t.entity; picker.value = this._config.entity || "";
    picker.addEventListener("value-changed", event => this._change("entity", event.detail.value));
    this.querySelector("label span").textContent = t.customTitle;
    const input = this.querySelector("input"); input.value = this._config.title || "";
    input.addEventListener("input", () => this._change("title", input.value));
  }
  _change(key, value) { this._config = { ...this._config, [key]: value }; this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })); }
}
if (!customElements.get("bticino-programs-card")) customElements.define("bticino-programs-card", BticinoProgramsCard);
if (!customElements.get("bticino-today-card")) customElements.define("bticino-today-card", BticinoTodayCard);
if (!customElements.get("bticino-programs-card-editor")) customElements.define("bticino-programs-card-editor", BticinoProgramsCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some(c => c.type === "bticino-programs-card")) window.customCards.push({ type: "bticino-programs-card", name: "BTicino Programs", description: "Weekly programs stored on the thermostat", preview: false });
if (!window.customCards.some(c => c.type === "bticino-today-card")) window.customCards.push({ type: "bticino-today-card", name: "BTicino Today", description: "Today's active program, current period and next change", preview: false });
