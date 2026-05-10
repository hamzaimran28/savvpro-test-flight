"use strict";

/**
 * FlightHub staff UI — calls FastAPI with fetch().
 * Expects ``window.FLIGHTHUB_API_BASE`` (defaults in index.html).
 */

const LOW_SEATS_BAND = 3;

/** Clears transient “Book” row highlight */
let flightRowFlashClearTimer = 0;

function flashFlightBookRow(rowEl) {
  if (!(rowEl instanceof HTMLElement)) return;
  document.querySelectorAll("tr.flight-row--flash").forEach((r) => {
    r.classList.remove("flight-row--flash");
  });
  window.clearTimeout(flightRowFlashClearTimer);
  rowEl.classList.add("flight-row--flash");
  flightRowFlashClearTimer = window.setTimeout(() => {
    rowEl.classList.remove("flight-row--flash");
  }, 2000);
}

const state = {
  flightsById: new Map(),
  mode: "all",
  seatChartTimer: null,
  /** Flight id backing the rendered chart (null until first successful GET). */
  seatMapFlightIdLoaded: null,
  /** Canonical label chosen from the seating grid. */
  selectedSeatLabel: "",
};

const uiBusy = {
  depth: 0,
  begin() {
    this.depth++;
    if (this.depth === 1) {
      document.getElementById("global-loading").classList.remove("hidden");
      document.body.classList.add("app-busy");
    }
  },
  end() {
    this.depth = Math.max(0, this.depth - 1);
    if (this.depth === 0) {
      document.getElementById("global-loading").classList.add("hidden");
      document.body.classList.remove("app-busy");
    }
  },
};

async function runWithBusy(job) {
  uiBusy.begin();
  try {
    return await job();
  } finally {
    uiBusy.end();
  }
}

function clearBookingGate() {
  const msg = document.getElementById("booking-gate-msg");
  msg.classList.add("hidden");
  msg.textContent = "";
  msg.classList.remove("alert-warn", "alert-neutral");
}

/** @param {'warn' | 'neutral'} variant */
function setBookingGateMessage(text, variant) {
  const msg = document.getElementById("booking-gate-msg");
  if (!text) {
    clearBookingGate();
    return;
  }
  msg.textContent = text;
  msg.classList.remove("hidden", "alert-warn", "alert-neutral");
  msg.classList.add(variant === "warn" ? "alert-warn" : "alert-neutral");
}

function apiBase() {
  const raw = (
    document.getElementById("api-base").value.trim() ||
    window.FLIGHTHUB_API_BASE ||
    ""
  ).replace(/\/$/, "");
  return raw;
}

async function fetchJson(method, url, bodyObj) {
  const opts = { method, headers: {} };
  if (bodyObj !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(bodyObj);
  }
  const res = await fetch(url, opts);
  const text = await res.text();
  let parsed = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = { detail: text };
    }
  }
  if (!res.ok) {
    const err = new Error(res.statusText || "Request failed");
    err.status = res.status;
    err.body = parsed;
    throw err;
  }
  return parsed;
}

function detailMessage(body) {
  if (!body) return "Unexpected error.";
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((d) => d.msg || JSON.stringify(d))
      .join(" · ");
  }
  return JSON.stringify(body);
}

function showBanner(kind, message) {
  const el = document.getElementById("status-banner");
  el.textContent = message;
  el.classList.remove("hidden", "error", "success", "info");
  el.classList.add(kind);
}

function clearBanner() {
  const el = document.getElementById("status-banner");
  el.classList.add("hidden");
  el.textContent = "";
}

const OVERLAY_AUTO_MS = 4500;

/** @type {number} */
let overlayTimer = 0;
/** @type {Element | null} */
let overlayRestoreFocus = null;

function hideActionOverlay() {
  window.clearTimeout(overlayTimer);
  overlayTimer = 0;
  const el = document.getElementById("action-overlay");
  if (!el) {
    return;
  }
  el.classList.add("hidden");
  el.setAttribute("aria-hidden", "true");
  el.classList.remove("action-overlay--success", "action-overlay--error", "action-overlay--info");
  document.body.classList.remove("overlay-open");
  if (
    overlayRestoreFocus &&
    typeof overlayRestoreFocus.focus === "function"
  ) {
    try {
      overlayRestoreFocus.focus({ preventScroll: true });
    } catch {
      /* noop */
    }
  }
  overlayRestoreFocus = null;
}

/**
 * Timed modal-style confirmation for impactful API outcomes.
 * @param {{ title: string, message: string, variant?: 'success'|'error'|'info', autoDismissMs?: number }} opts
 */
function showActionOverlay(opts) {
  const {
    title,
    message,
    variant = "success",
    autoDismissMs = OVERLAY_AUTO_MS,
  } = opts;
  const el = document.getElementById("action-overlay");
  const titleEl = document.getElementById("action-overlay-title");
  const msgEl = document.getElementById("action-overlay-msg");
  if (!el || !titleEl || !msgEl) {
    return;
  }

  window.clearTimeout(overlayTimer);
  overlayTimer = 0;

  const wasHidden = el.classList.contains("hidden");
  if (wasHidden) {
    overlayRestoreFocus = document.activeElement;
  }

  el.classList.remove("hidden", "action-overlay--success", "action-overlay--error", "action-overlay--info");
  el.classList.add(`action-overlay--${variant}`);
  titleEl.textContent = title;
  msgEl.textContent = message;
  el.setAttribute("aria-hidden", "false");
  document.body.classList.add("overlay-open");

  const btn = document.getElementById("action-overlay-dismiss");
  window.requestAnimationFrame(() => btn?.focus());

  overlayTimer = window.setTimeout(hideActionOverlay, autoDismissMs);
}

function wireActionOverlay() {
  const root = document.getElementById("action-overlay");
  const backdrop = root?.querySelector("[data-overlay-dismiss]");
  const dismiss = document.getElementById("action-overlay-dismiss");

  backdrop?.addEventListener("click", () => hideActionOverlay());
  dismiss?.addEventListener("click", () => hideActionOverlay());

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") {
      return;
    }
    if (!root || root.classList.contains("hidden")) {
      return;
    }
    ev.preventDefault();
    hideActionOverlay();
  });
}

function rowNumberPrefix(seatLabel) {
  const m = /^(\d+)/.exec(seatLabel);
  return m ? m[1] : "?";
}

function setSeatFieldValue(value) {
  const field = document.getElementById("booking-seat-field");
  field.value = value || "";
  state.selectedSeatLabel = value.trim() ? value.trim().toUpperCase() : "";
}

function clearSeatSelection({ rerender = false } = {}) {
  document.querySelectorAll(".seat-slot.selected").forEach((el) =>
    el.classList.remove("selected"),
  );
  setSeatFieldValue("");
  document.getElementById("btn-clear-seat").classList.add("hidden");
  if (rerender) {
    const raw = document.getElementById("booking-flight-id").value.trim();
    const fid = Number.parseInt(raw, 10);
    if (!Number.isNaN(fid)) {
      void loadSeatChart(fid);
    }
  }
}

const SEAT_CHART_DEFAULT_HINT =
  "Cabin refreshes when Flight ID changes. Green = available · red = booked · blue = selected.";
const PLACEHOLDER_DEFAULT_TITLE = "Cabin not loaded";
const PLACEHOLDER_DEFAULT_SUB =
  "Enter a Flight ID above (from the schedule table) to load the interactive seat map.";

function letterFromSeatNumber(seatNumber) {
  const m = /^(\d+)([A-Za-z]+)$/.exec(String(seatNumber || ""));
  return m ? m[2].toUpperCase() : "?";
}

/** Column letter index 0 = A, aligned with ``columns_per_full_row`` from the API. */
function columnIndexFromSeat(seatNumber) {
  const letter = letterFromSeatNumber(seatNumber);
  if (letter === "?" || letter.length !== 1) return -1;
  const code = letter.charCodeAt(0) - 65;
  return code >= 0 && code <= 25 ? code : -1;
}

/** Left block column indices (window) | aisle | right block — matches backend row-major A→F. */
function aisleSplitColumnIndices(columnsPerFullRow) {
  const cut = Math.ceil(Number(columnsPerFullRow) / 2) || 3;
  const left = [];
  const right = [];
  for (let c = 0; c < columnsPerFullRow; c++) {
    (c < cut ? left : right).push(c);
  }
  return [left, right];
}

function tilesByColumnIndex(tiles) {
  const m = new Map();
  for (const t of tiles) {
    const ci = columnIndexFromSeat(t.seat_number);
    if (ci >= 0) {
      m.set(ci, t);
    }
  }
  return m;
}

function showSeatChartStage() {
  document.getElementById("seat-chart-placeholder").classList.add("hidden");
  document.getElementById("seat-chart-stage").classList.remove("hidden");
}

/** Idle / error: fuselage stays visible with a message; chart chrome is cleared. */
function resetSeatChartUI(title, sub) {
  const stage = document.getElementById("seat-chart-stage");
  const placeholder = document.getElementById("seat-chart-placeholder");
  const chart = document.getElementById("seat-chart");
  const headers = document.getElementById("seat-chart-headers");
  const hint = document.getElementById("seat-chart-hint");

  stage.classList.add("hidden");
  placeholder.classList.remove("hidden");
  chart.innerHTML = "";
  headers.innerHTML = "";
  headers.classList.add("hidden");

  document.getElementById("seat-chart-placeholder-title").textContent =
    title || PLACEHOLDER_DEFAULT_TITLE;
  document.getElementById("seat-chart-placeholder-sub").textContent =
    sub || PLACEHOLDER_DEFAULT_SUB;

  document.getElementById("btn-clear-seat").classList.add("hidden");
  state.seatMapFlightIdLoaded = null;
  hint.textContent = SEAT_CHART_DEFAULT_HINT;
}

function makeCabinAisle() {
  const aisle = document.createElement("div");
  aisle.className = "cabin-aisle";
  aisle.setAttribute("aria-hidden", "true");
  const stripe = document.createElement("span");
  stripe.className = "cabin-aisle-stripe";
  aisle.appendChild(stripe);
  return aisle;
}

function renderLetterHeaderRow(columnsPerFullRow) {
  const rowWrap = document.createElement("div");
  rowWrap.className = "cabin-row cabin-row--header";

  const rowNum = document.createElement("div");
  rowNum.className = "cabin-row-num cabin-row-num--header";
  rowNum.textContent = "";
  rowNum.setAttribute("aria-hidden", "true");

  const letters = [];
  for (let c = 0; c < columnsPerFullRow; c++) {
    letters.push(String.fromCharCode(65 + c));
  }
  const [leftCols, rightCols] = aisleSplitColumnIndices(columnsPerFullRow);

  const seatsOuter = document.createElement("div");
  seatsOuter.className = "cabin-row-seats";

  const leftBlock = document.createElement("div");
  leftBlock.className = "seat-block seat-block--header";
  leftCols.forEach((ci) => {
    const span = document.createElement("span");
    span.className = "cabin-col-label";
    span.textContent = letters[ci];
    leftBlock.appendChild(span);
  });

  const rightBlock = document.createElement("div");
  rightBlock.className = "seat-block seat-block--header";
  rightCols.forEach((ci) => {
    const span = document.createElement("span");
    span.className = "cabin-col-label";
    span.textContent = letters[ci];
    rightBlock.appendChild(span);
  });

  seatsOuter.appendChild(leftBlock);
  seatsOuter.appendChild(makeCabinAisle());
  seatsOuter.appendChild(rightBlock);

  rowWrap.appendChild(rowNum);
  rowWrap.appendChild(seatsOuter);
  return rowWrap;
}

function renderAbsentSeatCell() {
  const gap = document.createElement("div");
  gap.className = "cabin-slot-absent";
  gap.setAttribute("aria-hidden", "true");
  const dash = document.createElement("span");
  dash.className = "cabin-absent-dash";
  dash.textContent = "—";
  gap.appendChild(dash);
  return gap;
}

function renderSeatButtonForTile(tile, letter, btnClear) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "seat-slot";
  btn.dataset.seat = tile.seat_number;
  btn.textContent = letter;
  btn.setAttribute(
    "aria-label",
    tile.available
      ? `Seat ${tile.seat_number}, available`
      : `Seat ${tile.seat_number}, booked`,
  );
  if (!tile.available) {
    btn.classList.add("booked");
    btn.disabled = true;
    btn.title = `${tile.seat_number} · booked`;
  } else {
    btn.classList.add("available");
    btn.title = `${tile.seat_number} · tap to select`;
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      document.querySelectorAll(".seat-slot.selected").forEach((el) =>
        el.classList.remove("selected"),
      );
      btn.classList.add("selected");
      setSeatFieldValue(tile.seat_number);
      btnClear.classList.remove("hidden");
      refreshBookingGate();
      document.getElementById("booking-seat-field").dispatchEvent(
        new Event("input", { bubbles: true }),
      );
    });
  }
  if (
    state.selectedSeatLabel &&
    tile.seat_number.toUpperCase() === state.selectedSeatLabel &&
    tile.available
  ) {
    btn.classList.add("selected");
  }
  return btn;
}

function renderSeatBlockForIndices(columnIndices, byCol, btnClear) {
  const block = document.createElement("div");
  block.className = "seat-block";
  for (const ci of columnIndices) {
    const tile = byCol.get(ci);
    if (!tile) {
      block.appendChild(renderAbsentSeatCell());
      continue;
    }
    const letter = letterFromSeatNumber(tile.seat_number);
    block.appendChild(renderSeatButtonForTile(tile, letter, btnClear));
  }
  return block;
}

function renderCabinSeatRow(tiles, columnsPerFullRow, btnClear) {
  const rowWrap = document.createElement("div");
  rowWrap.className = "cabin-row";

  const rowNum = document.createElement("div");
  rowNum.className = "cabin-row-num";

  let rowLabel = "?";
  if (tiles.length > 0) {
    rowLabel = escapeHtml(rowNumberPrefix(tiles[0].seat_number));
  }

  rowNum.innerHTML =
    `<span class="cabin-row-num-main">${rowLabel}</span>` +
    `<span class="cabin-row-num-sub muted">row</span>`;

  const byCol = tilesByColumnIndex(tiles);
  const [leftCols, rightCols] = aisleSplitColumnIndices(columnsPerFullRow);

  const seatsOuter = document.createElement("div");
  seatsOuter.className = "cabin-row-seats";
  seatsOuter.appendChild(renderSeatBlockForIndices(leftCols, byCol, btnClear));
  seatsOuter.appendChild(makeCabinAisle());
  seatsOuter.appendChild(
    renderSeatBlockForIndices(rightCols, byCol, btnClear),
  );

  rowWrap.appendChild(rowNum);
  rowWrap.appendChild(seatsOuter);
  return rowWrap;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadSeatChart(flightId) {
  const chart = document.getElementById("seat-chart");
  const headers = document.getElementById("seat-chart-headers");
  const hint = document.getElementById("seat-chart-hint");
  const btnClear = document.getElementById("btn-clear-seat");

  if (!Number.isFinite(flightId) || flightId < 1) {
    resetSeatChartUI();
    clearSeatSelection({ rerender: false });
    return;
  }

  showSeatChartStage();
  hint.textContent = "Loading seating layout…";
  headers.innerHTML = "";
  headers.classList.add("hidden");
  chart.innerHTML =
    '<p class="cabin-loading muted" role="status">Fetching seat map…</p>';

  try {
    const base = apiBase();
    const data = await fetchJson(
      "GET",
      `${base}/flights/${flightId}/seat-map`,
    );
    state.seatMapFlightIdLoaded = flightId;
    hint.textContent = `${data.total_seats} cabin positions · ${data.columns_per_full_row} columns (A→). Shorter rows show a dash where this aircraft has no seat. Tap a green seat to select; your pick shows in blue.`;

    chart.innerHTML = "";
    headers.innerHTML = "";

    if (!data.rows.length) {
      chart.innerHTML =
        '<p class="muted">No seating rows returned for this flight.</p>';
    } else {
      headers.classList.remove("hidden");
      headers.appendChild(
        renderLetterHeaderRow(data.columns_per_full_row || 6),
      );
      const cols = data.columns_per_full_row || 6;
      for (const tiles of data.rows) {
        chart.appendChild(renderCabinSeatRow(tiles, cols, btnClear));
      }
    }

    if (state.selectedSeatLabel) {
      let stillOk = false;
      for (const row of data.rows) {
        for (const tile of row) {
          if (
            tile.seat_number.toUpperCase() === state.selectedSeatLabel &&
            tile.available
          ) {
            stillOk = true;
          }
        }
      }
      if (!stillOk) {
        clearSeatSelection({ rerender: false });
      } else {
        btnClear.classList.remove("hidden");
      }
    }
  } catch (err) {
    const detail = detailMessage(err.body) || err.message;
    resetSeatChartUI(
      "Couldn’t load cabin",
      `${err.status ? `Server returned ${err.status}. ` : ""}${detail}`,
    );
    clearSeatSelection({ rerender: false });
  }
}

function scheduleSeatChartLoad() {
  if (state.seatChartTimer) {
    clearTimeout(state.seatChartTimer);
  }
  state.seatChartTimer = setTimeout(() => {
    const raw = document.getElementById("booking-flight-id").value.trim();
    const fid = Number.parseInt(raw, 10);
    if (!raw || Number.isNaN(fid)) {
      resetSeatChartUI();
      clearSeatSelection({ rerender: false });
      refreshBookingGate();
      return;
    }
    void loadSeatChart(fid).finally(() => {
      refreshBookingGate();
    });
  }, 150);
}

function formatMoney(amount) {
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDeparture(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatDurationMinutes(mins) {
  const m = Number(mins);
  if (Number.isNaN(m)) return String(mins);
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h === 0) return `${mm}m`;
  return `${h}h ${mm.toString().padStart(2, "0")}m`;
}

function rebuildFlightIndex(flights) {
  state.flightsById = new Map(
    flights.map((f) => [Number(f.id), f]),
  );
}

function refreshBookingGate() {
  const fidHint = document.getElementById("booking-flight-id-hint");
  const submit = document.getElementById("btn-submit-booking");
  const input = document.getElementById("booking-flight-id");
  const seatField = document.getElementById("booking-seat-field");
  const fid = Number.parseInt(input.value, 10);
  clearBookingGate();
  if (fidHint) {
    fidHint.textContent = "";
    fidHint.className = "field-feedback";
  }
  submit.disabled = false;

  if (!input.value.trim()) {
    return;
  }

  if (Number.isNaN(fid)) {
    submit.disabled = true;
    setBookingGateMessage("Enter a valid numeric flight ID.", "warn");
    return;
  }

  document.querySelectorAll(".seat-slot.available").forEach((btn) => {
    btn.disabled = false;
  });

  const flight = state.flightsById.get(fid);
  if (!flight) {
    setBookingGateMessage(
      "This flight ID is not on the loaded schedule below. The cabin map still loads if the backend has the flight.",
      "neutral",
    );
    if (fidHint) {
      fidHint.textContent = "Not in current schedule list";
      fidHint.classList.add("field-feedback-error");
    }
  }

  const availGuess = flight ? Number(flight.seats_available) : null;

  const seatChosen = seatField.value.trim();
  const flightSync = seatMapMatchesFlight(fid);
  if (seatChosen && flightSync && !isSeatSelectableInChart(seatChosen)) {
    setBookingGateMessage(
      "Chosen seat is booked or not available in the map. Pick another seat or reload the chart.",
      "warn",
    );
    submit.disabled = true;
    return;
  }

  if (availGuess !== null && availGuess <= 0) {
    setBookingGateMessage(
      "This flight is sold out on the schedule. You can inspect the map; confirming a booking stays disabled.",
      "warn",
    );
    submit.disabled = true;
    return;
  }

  if (!seatChosen && flightSync && state.seatMapFlightIdLoaded === fid) {
    setBookingGateMessage(
      "Select an available seat on the cabin map (green); it appears blue when selected.",
      "neutral",
    );
  }
}

function seatMapMatchesFlight(flightId) {
  return state.seatMapFlightIdLoaded === flightId;
}

function isSeatSelectableInChart(label) {
  const up = label.trim().toUpperCase();
  for (const btn of document.querySelectorAll(".seat-slot.available")) {
    if ((btn.dataset.seat || "").toUpperCase() === up && !btn.disabled) {
      return true;
    }
  }
  return false;
}


function emptyFlightsCaption() {
  if (state.mode === "search") {
    return "No flights matched your filters. Adjust origin, destination, or date and try again.";
  }
  return "No flights in the schedule. Refresh the list or verify the backend connection.";
}

function renderFlightRows(flights) {
  const tbody = document.getElementById("flights-tbody");
  tbody.innerHTML = "";

  if (!flights.length) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    const td = document.createElement("td");
    td.colSpan = 8;
    td.innerHTML =
      `<span class="empty-cell-icon" aria-hidden="true">✈</span>` +
      `<span class="muted">${emptyFlightsCaption()}</span>`;
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const f of flights) {
    const tr = document.createElement("tr");
    const avail = Number(f.seats_available);
    const soldOut = avail <= 0;
    const lowSeats =
      !soldOut &&
      avail > 0 &&
      avail <= LOW_SEATS_BAND &&
      avail < Number(f.total_seats);
    tr.classList.add("flight-row");
    tr.dataset.flightId = String(f.id);
    if (soldOut) {
      tr.classList.add("sold-out-row");
    } else if (lowSeats) {
      tr.classList.add("low-seats-row");
    }

    const idTd = document.createElement("td");
    idTd.textContent = f.id;

    const originTd = document.createElement("td");
    originTd.className = "route-cell";
    originTd.textContent = f.origin;

    const destTd = document.createElement("td");
    destTd.className = "route-cell";
    destTd.textContent = f.destination;

    [idTd, originTd, destTd].forEach((td) => tr.appendChild(td));

    const tdTime = document.createElement("td");
    tdTime.textContent = formatDeparture(f.departure_datetime);
    tr.appendChild(tdTime);

    const tdDur = document.createElement("td");
    tdDur.textContent = formatDurationMinutes(f.duration_minutes);
    tr.appendChild(tdDur);

    const tdPrice = document.createElement("td");
    tdPrice.textContent = formatMoney(f.price_per_seat);
    tr.appendChild(tdPrice);

    const availTd = document.createElement("td");
    availTd.className = "seats-cell";
    if (soldOut) {
      availTd.innerHTML =
        `<span class="seats-pill seats-pill--none seats-cell-num">0</span>` +
        `<span class="badge-sold-out-table">Full</span>`;
    } else {
      const pill = document.createElement("span");
      pill.className =
        lowSeats
          ? "seats-pill seats-pill--low seats-cell-num"
          : "seats-pill seats-pill--ok seats-cell-num";
      pill.textContent = String(avail);
      if (lowSeats) {
        pill.title = "Limited inventory";
      }
      availTd.appendChild(pill);
    }
    tr.appendChild(availTd);

    const actionTd = document.createElement("td");
    actionTd.className = "book-row-actions";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-secondary btn-book-mini";
    btn.textContent = soldOut ? "Unavailable" : "Book";

    btn.disabled = soldOut;
    if (soldOut) {
      btn.title = "Sold out";
    } else {
      btn.title = "Prefill Flight ID";
      btn.addEventListener("click", () => {
        document.getElementById("booking-flight-id").value = String(f.id);
        refreshBookingGate();
        scheduleSeatChartLoad();
        const section = document.getElementById("section-booking");
        const fidInput = document.getElementById("booking-flight-id");
        section?.scrollIntoView({ behavior: "smooth", block: "start" });
        flashFlightBookRow(tr);
        window.setTimeout(() => {
          fidInput?.focus({ preventScroll: true });
        }, 350);
      });
    }
    actionTd.appendChild(btn);
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  }
}

function setFlightsModeLabel(text) {
  document.getElementById("flights-mode-label").textContent = text;
}

async function loadAllFlights(options = {}) {
  const { keepBanner = false } = options;
  return runWithBusy(async () => {
    if (!keepBanner) {
      clearBanner();
    }
    const base = apiBase();
    const data = await fetchJson("GET", `${base}/flights`);
    state.mode = "all";
    rebuildFlightIndex(data);
    setFlightsModeLabel("Showing: all flights in schedule");
    renderFlightRows(data);
    refreshBookingGate();
    scheduleSeatChartLoad();
  });
}

async function runFlightSearch(origin, destination, departure_date, options = {}) {
  const { keepBanner = false } = options;
  return runWithBusy(async () => {
    if (!keepBanner) {
      clearBanner();
    }
    const base = apiBase();
    const params = new URLSearchParams();
    if (origin) params.set("origin", origin);
    if (destination) params.set("destination", destination);
    if (departure_date) params.set("departure_date", departure_date);
    const qs = params.toString();
    const url = qs ? `${base}/flights/search?${qs}` : `${base}/flights/search`;
    const data = await fetchJson("GET", url);
    state.mode = "search";
    /** Search results omit sold-out flights; index only these rows — booking helper may warn on unknown IDs. */
    rebuildFlightIndex(data);
    const desc = qs
      ? "Filtered matches (inventory > 0 only)"
      : "All flights with seats (no filters)";
    setFlightsModeLabel(`Showing: ${desc}`);
    renderFlightRows(data);
    refreshBookingGate();
    scheduleSeatChartLoad();
  });
}

function renderLookupRows(rows) {
  const tbody = document.getElementById("lookup-tbody");
  tbody.innerHTML = "";

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    const td = document.createElement("td");
    td.colSpan = 6;
    td.innerHTML =
      `<span class="empty-cell-icon" aria-hidden="true">📋</span>` +
      `<span class="muted">No bookings matched. Try reference or passenger name.</span>`;
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const b of rows) {
    const tr = document.createElement("tr");
    const fd = `${b.flight.origin} → ${b.flight.destination}`;
    const when = formatDeparture(b.flight.departure_datetime);

    [[b.booking_reference], [`${fd} (${when})`], [b.passenger_full_name], [b.seat_number]].forEach(
      ([text]) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      },
    );

    const statusTd = document.createElement("td");
    const badge = document.createElement("span");
    const raw = String(b.booking_status || "").toUpperCase();
    badge.className =
      raw === "CANCELLED"
        ? "badge-status badge-status--cancelled"
        : "badge-status badge-status--confirmed";
    badge.textContent = raw;
    statusTd.appendChild(badge);
    tr.appendChild(statusTd);

    const createdTd = document.createElement("td");
    createdTd.textContent = formatDeparture(b.created_at);
    tr.appendChild(createdTd);

    tbody.appendChild(tr);
  }
}

function syncLookupFields() {
  const mode =
    document.querySelector('input[name="lookup_mode"]:checked').value ||
    "reference";
  const refWrap = document.getElementById("lookup-ref-wrap");
  const nameWrap = document.getElementById("lookup-name-wrap");
  const refInput = document.getElementById("lookup-reference");
  const nameInput = document.getElementById("lookup-name");

  if (mode === "reference") {
    refWrap.classList.remove("hidden");
    nameWrap.classList.add("hidden");
    nameInput.value = "";
    nameInput.removeAttribute("required");
    refInput.setAttribute("required", "");
  } else {
    refWrap.classList.add("hidden");
    nameWrap.classList.remove("hidden");
    refInput.value = "";
    refInput.removeAttribute("required");
    nameInput.setAttribute("required", "");
  }
}

function wirePassportFeedback() {
  const el = document.getElementById("passport-number");
  const fb = document.getElementById("passport-feedback");
  if (!el || !fb) {
    return;
  }
  el.addEventListener("input", () => {
    fb.textContent = "";
    fb.className = "field-feedback";
    el.classList.remove("field-invalid");
  });
  el.addEventListener("blur", () => {
    if (!el.value.trim()) {
      return;
    }
    if (!el.validity.valid) {
      el.classList.add("field-invalid");
      fb.textContent = "Only letters and digits.";
      fb.className = "field-feedback field-feedback-error";
    }
  });
}

function wireForms() {
  document
    .getElementById("api-base")
    .addEventListener("change", () => {
      window.FLIGHTHUB_API_BASE = apiBase();
    });

  wirePassportFeedback();

  document.getElementById("btn-test-api").addEventListener("click", async () => {
    await runWithBusy(async () => {
      try {
        clearBanner();
        const base = apiBase();
        await fetchJson("GET", `${base}/flights`);
        showActionOverlay({
          variant: "success",
          title: "Connected",
          message: `FlightHub reached ${base}. You can search and book.`,
        });
      } catch (e) {
        showActionOverlay({
          variant: "error",
          title: "Connection failed",
          message: `${e.status ?? "?"} · ${detailMessage(e.body) || e.message}`,
        });
      }
    });
  });

  document
    .getElementById("btn-refresh-flights")
    .addEventListener("click", async () => {
      try {
        await loadAllFlights();
        showActionOverlay({
          variant: "success",
          title: "Schedule updated",
          message: "The flight table now reflects the latest data from the server.",
        });
      } catch (e) {
        showActionOverlay({
          variant: "error",
          title: "Could not refresh schedule",
          message: detailMessage(e.body) || e.message,
        });
      }
    });

  document
    .getElementById("search-form")
    .addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      const origin = (fd.get("origin") || "").toString().trim();
      const destination = (fd.get("destination") || "").toString().trim();
      const departure_date =
        (fd.get("departure_date") || "").toString().trim() || "";

      try {
        await runFlightSearch(origin, destination, departure_date);
        showBanner("info", "Showing flights with available seats.");
      } catch (e) {
        showBanner(
          "error",
          `Search failed: ${detailMessage(e.body) || e.message}`,
        );
      }
    });

  document.querySelector("#booking-flight-id").addEventListener("input", () => {
    refreshBookingGate();
    scheduleSeatChartLoad();
  });

  document.getElementById("btn-clear-seat").addEventListener("click", () => {
    clearSeatSelection({ rerender: true });
    refreshBookingGate();
  });

  document.getElementById("booking-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!ev.target.reportValidity()) {
      return;
    }
    clearBanner();
    const fd = new FormData(ev.target);
    const seatVal = (
      document.getElementById("booking-seat-field").value || ""
    ).trim();

    refreshBookingGate();
    if (document.getElementById("btn-submit-booking").disabled) {
      showBanner(
        "error",
        "Cannot book right now — check flight availability or seat availability.",
      );
      return;
    }

    const fidParsed = Number.parseInt(String(fd.get("flight_id")), 10);

    if (!seatVal) {
      showBanner("error", "Select an available seat on the cabin map first (green seat; blue when picked).");
      return;
    }

    if (seatMapMatchesFlight(fidParsed) && !isSeatSelectableInChart(seatVal)) {
      showBanner("error", "That seat is unavailable in the cabin chart.");
      return;
    }

    const payload = {
      flight_id: fidParsed,
      passenger_full_name: (fd.get("passenger_full_name") || "").toString(),
      passport_number: (fd.get("passport_number") || "").toString(),
      seat_number: seatVal,
    };

    try {
      await runWithBusy(async () => {
        const base = apiBase();
        const booking = await fetchJson("POST", `${base}/bookings`, payload);
        ev.target.reset();
        clearSeatSelection({ rerender: false });
        resetSeatChartUI();
        showActionOverlay({
          variant: "success",
          title: "Booking confirmed",
          message: `${booking.booking_reference} · ${booking.booking_status} · seat ${booking.seat_number}`,
        });
        if (state.mode === "search") {
          await runFlightSearchFromFormSticky({ keepBanner: true });
        } else {
          await loadAllFlights({ keepBanner: true });
        }
        renderLookupRows([booking]);
        scheduleSeatChartLoad();
      });
    } catch (e) {
      showActionOverlay({
        variant: "error",
        title: "Booking not completed",
        message: `${e.status ? `${e.status} · ` : ""}${detailMessage(e.body) || e.message}`,
      });
    }
  });

  document
    .querySelectorAll('input[name="lookup_mode"]')
    .forEach((r) =>
      r.addEventListener("change", () => syncLookupFields()),
    );
  syncLookupFields();

  document.getElementById("lookup-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearBanner();
    const base = apiBase();
    const params = new URLSearchParams();

    const mode =
      document.querySelector('input[name="lookup_mode"]:checked').value;
    if (mode === "reference") {
      const ref = (
        document.getElementById("lookup-reference").value || ""
      ).trim();
      if (!ref) {
        showBanner("error", "Enter a booking reference.");
        return;
      }
      params.set("booking_reference", ref);
    } else {
      const name = (document.getElementById("lookup-name").value || "").trim();
      if (!name) {
        showBanner("error", "Enter a passenger full name.");
        return;
      }
      params.set("passenger_full_name", name);
    }

    try {
      await runWithBusy(async () => {
        const rows = await fetchJson(
          "GET",
          `${base}/bookings?${params.toString()}`,
        );
        renderLookupRows(Array.isArray(rows) ? rows : []);
        const n = Array.isArray(rows) ? rows.length : 0;
        showActionOverlay({
          variant: "info",
          title: "Lookup complete",
          message:
            n === 0
              ? "No rows matched — try another reference or passenger name."
              : `Found ${n} booking record${n === 1 ? "" : "s"}. See the table below.`,
        });
      });
    } catch (e) {
      showActionOverlay({
        variant: "error",
        title: "Lookup failed",
        message: detailMessage(e.body) || e.message,
      });
    }
  });

  document.getElementById("cancel-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearBanner();
    const ref = (
      document.getElementById("cancel-reference").value || ""
    ).trim();

    try {
      await runWithBusy(async () => {
        const base = apiBase();
        const enc = encodeURIComponent(ref);
        const booking = await fetchJson(
          "DELETE",
          `${base}/bookings/${enc}`,
        );
        showActionOverlay({
          variant: "success",
          title: "Cancellation complete",
          message: `${ref} is now ${booking.booking_status}. The seat is available again.`,
        });
        ev.target.reset();
        if (state.mode === "search") {
          await runFlightSearchFromFormSticky({ keepBanner: true });
        } else {
          await loadAllFlights({ keepBanner: true });
        }
        scheduleSeatChartLoad();
      });
    } catch (e) {
      showActionOverlay({
        variant: "error",
        title: "Cancellation failed",
        message: `${e.status ? `${e.status} · ` : ""}${detailMessage(e.body) || e.message}`,
      });
    }
  });
}

/** Re-run search with whatever is in search form inputs (same GET query). */
async function runFlightSearchFromFormSticky(options = {}) {
  const sf = document.getElementById("search-form");
  const fd = new FormData(sf);
  await runFlightSearch(
    (fd.get("origin") || "").trim(),
    (fd.get("destination") || "").trim(),
    (fd.get("departure_date") || "").trim(),
    options,
  );
}

async function bootstrap() {
  document.getElementById("api-base").value =
    window.FLIGHTHUB_API_BASE || document.getElementById("api-base").value;

  wireForms();
  wireActionOverlay();

  try {
    await loadAllFlights();
  } catch (_e) {
    showBanner(
      "info",
      "Could not load flights on startup — check backend URL or start FastAPI.",
    );
  }

  refreshBookingGate();
  scheduleSeatChartLoad();
}

document.addEventListener("DOMContentLoaded", bootstrap);
