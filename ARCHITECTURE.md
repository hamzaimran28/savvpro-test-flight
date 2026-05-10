# FlightHub — Architecture

Technical overview of how the system is structured and how booking and inventory behave. For **run instructions**, see **`README.md`**. For **operator workflows**, see **`USER_GUIDE.md`**.

---

## 1. System overview

- **Browser** — staff UI (static files; `fetch` to API).
- **Express** — serves `frontend/public/` only; no business logic.
- **FastAPI** — JSON REST API, validation, error mapping.
- **SQLite** — single-file database (path from `DATABASE_URL`, default `./flighthub.db` with cwd `backend/`).

API routes live at **`/flights`** and **`/bookings`**. OpenAPI UI: **`/docs`**.

---

## 2. Code layout

| Area | Responsibility |
|------|----------------|
| **`routers/`** | HTTP mapping, Pydantic in/out, thin handlers |
| **`services/`** | Transactions, booking rules, inventory, reconciliation |
| **`models/`** | SQLAlchemy ORM (`Flight`, `Booking`) |
| **`schemas/`** | Pydantic request/response shapes |
| **`api/deps.py`** | DB session dependency, booking lookup query parsing |
| **`api/exception_handlers.py`** | Domain errors → **404 / 409 / 422** (etc.) |
| **`domain/cabin_layout.py`** | Seat catalogue and layout for this assessment’s simplified cabin |

Tests: **`backend/tests/`** (pytest + isolated DB). Scripts: **`backend/scripts/verify_*.py`**.

---

## 3. Service-layer design

**Routers do not own business rules.** They validate input and call **`flight_service`** or **`booking_service`**. Those services:

- Own **transaction boundaries** (`commit` / `rollback`).
- Enforce **seat availability**, **uniqueness of active seats**, and **post-write reconciliation** of stored counts.
- Stay callable from tests without going through HTTP.

This keeps concurrency and inventory logic in one place and avoids duplicating policy in the UI or multiple handlers.

---

## 4. Database schema (conceptual)

**`flights`** — `id`, route, `departure_datetime` (timezone-aware), `duration_minutes`, `price_per_seat`, `total_seats` (fixed capacity), **`seats_available`** (persisted, must stay consistent with bookings after each write — see §6).

**`bookings`** — `booking_reference` (unique), `flight_id`, `passenger_full_name`, `passport_number`, `seat_number`, `booking_status` (`CONFIRMED` | `CANCELLED`), timestamps, optional `cancelled_at`.

**Seat reuse after cancel:** SQLite **partial unique index** on `(flight_id, seat_number)` **only where** `booking_status = 'CONFIRMED'`, so a cancelled row does not block the same seat label for a new confirmed booking.

---

## 5. Booking lifecycle

1. **Create** — Client sends `flight_id`, passenger fields, `seat_number`. Server validates the flight and that the seat exists on that aircraft’s layout, then attempts reservation inside one transaction (§6).
2. **Confirm** — Success returns **201** and a generated **booking reference**; the flight’s open-seat picture updates.
3. **Lookup** — `GET /bookings` with **exactly one** of `booking_reference` or `passenger_full_name` (name match is case-insensitive).
4. **Cancel** — `DELETE /bookings/{ref}` or `POST /bookings/{ref}/cancel`. If already cancelled → **409**; unknown ref → **404**; success → status `CANCELLED` and inventory reconciled.

---

## 6. Seat inventory strategy

**Two related notions:**

1. **Derived open seats** — Computed from **`total_seats`** minus the set of **distinct, normalized** seat codes held by **CONFIRMED** bookings, intersected with the **known seat catalogue** for that aircraft. The **seat map** and **JSON `seats_available` in flight responses** use this derivation so clients see the same numbers as the diagram.
2. **Persisted `seats_available`** on `flights` — Used for an **atomic guard** during booking (see concurrency). After successful writes it is **reconciled** to match the derived value so it does not drift under parallel traffic.

**Reconciliation** (`flight_service.reconcile_flight_inventory`) resets the stored column from derived truth. It runs:

- At the **start** of **`create_booking`** (repair before attempting decrement).
- **After** flushing a new **`Booking`** and **before** **`commit`** (fixes drift when many threads decrement/rollback).
- After marking a booking **CANCELLED** (**cancel** path does not hand-adjust `+1`; it reconciles).

---

## 7. Concurrency & overbooking prevention

**Goal:** Never confirm more passengers than physical seats when multiple requests overlap.

**Pattern:**

1. Inside one transaction: reconcile, check stored `seats_available`, then run a single **`UPDATE … SET seats_available = seats_available - 1`** with **`WHERE id = ? AND seats_available > 0`**.
2. Only if **exactly one row** is updated proceed to insert the **`CONFIRMED`** booking.
3. On **unique-index violation** (narrow race on the same seat), **rollback** the whole transaction and return **409**.

SQLite serializes writers on the same flight row; the conditional update ensures **only one winner** claims the last seat compared to naive read-then-write.

Stress-style checks live in **`scripts/verify_overbooking_concurrency.py`** (parallel workers).

---

## 8. List vs search

- **`GET /flights`** — Every flight row (sold-out included). Sort by departure.
- **`GET /flights/search`** — Optional **`origin`**, **`destination`**, **`departure_date`** filters (UTC date window); responses omit flights with **no** derived open seats.

---

## 9. Frontend coupling

The UI reads **`FlightOut`** payloads whose **`seats_available`** already reflects derived inventory. Client-side checks (e.g. disabling **Book**) are **hints only** — the API remains authoritative.

---

## 10. Trade-offs & simplifications

| Topic | Choice |
|-------|--------|
| Auth | None — assumed internal network |
| Payments / GDS | Out of scope |
| Cabin layout | Deterministic simplified grid (domain module), not real airline configs |
| DB | SQLite — simple ops; **`SQLITE_BUSY`** mitigated via connection timeout |
| Idempotent cancel | **Repeat cancel → 409**, not silent success |

---

## 11. Testing

**`pytest`** — isolated SQLite file per test (`tests/conftest.py`). Business scenarios: sold-out conflict, cancel restores counts, search filters.

Subprocess tests optionally run **`scripts/verify_*.py`** against the same logic paths with temporary databases.
