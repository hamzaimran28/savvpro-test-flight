# FlightHub — System architecture (as implemented)

This document matches the **current** codebase: FastAPI routers, SQLite, service-layer transactions, deterministic seat maps, Express-hosted static UI, and pytest tooling.

---

## 1. Goals & scope

**In scope**

- Browse full schedule (**including** sold-out flights).
- Search flights with inventory filters (derived open seats **`> 0`**).
- Create **CONFIRMED** bookings (passenger + canonical seat code).
- Look up bookings by reference or passenger name.
- Cancel bookings (**409** if already cancelled).

**Out of scope**

- Payments, airline GDS/integration, authentication, waitlists.

**Stack**

- **Backend:** FastAPI · SQLAlchemy 2 · SQLite (`backend/app/`).
- **Frontend:** Plain HTML/CSS/JS; **Express** only serves **`frontend/public`**.
- **No** global `/api` prefix — routes mount at **`/flights`** and **`/bookings`**.

---

## 2. Logical architecture

```
Browser (FlightHub UI, :3000)
        │ fetch JSON (CORS limited to localhost/127.0.0.1 :3000)
        ▼
FastAPI (:8000)  ──►  routers (HTTP) ──►  services (transactions + rules)
                              │                    │
                              └────────────────────┴──►  SQLite file
```

Routers stay **thin**: validate with Pydantic / dependencies, call **one service** pathway, rely on **`register_exception_handlers`** for **404** / **409** / **422** / **500** domain mapping.

---

## 3. Data model (implemented)

### 3.1 `Flight`

- **`total_seats`**: immutable capacity for catalogue generation (`app/domain/cabin_layout.py`).
- **`seats_available`**: persisted column updated by booking/cancel flows; **must** be reconciled with derived open seats **before commit** after writes (see §4).

### 3.2 `Booking`

- **`booking_reference`**: unique, server-generated.
- **`booking_status`**: `CONFIRMED` | `CANCELLED`.
- **`cancelled_at`**: set when cancelled.
- **Partial unique index** (SQLite): **`(flight_id, seat_number)`** unique **where `booking_status = 'CONFIRMED'`** (`app/models/booking.py`). Cancelled rows can free a seat label for reuse.

---

## 4. Seat inventory, derivation & concurrency

### 4.1 Source of truth for “how many seats are left?”

**`flight_service.derive_seats_open(session, flight)`** computes:

\[
\text{open} = \text{total\_seats} - |\{\text{normalized confirmed seat codes}\}\cap\text{catalogue}|
\]

Occupied seats use **`normalize_seat_code`** so **`1a`** matches **`1A`** in logic. This matches **`GET /flights/{id}/seat-map`** tile availability (`flight_service.canonical_positions_with_confirmed_booking` / `SeatMapTile.available`).

**`flight_service.flight_as_out`** always returns **`seats_available=derive_seats_open(...)`** so clients never see a stale scalar if the DB column drifted.

### 4.2 Reconciliation

**`flight_service.reconcile_flight_inventory(session, flight)`** assigns:

`flight.seats_available ← derive_seats_open(session, flight)`

**When it runs**

- At the **start** of **`create_booking`** (repair drift before guarded decrement).
- **Immediately after flushing** the new **`Booking`** row and **before** **`commit`** (**fix:** keeps the persisted column aligned under parallel decrements / rollbacks).
- After cancellation status change **before commit** (**`cancel_booking`**).

Cancellation **does not** manually increment the counter; **`reconcile_flight_inventory`** rebuilds from confirmed rows.

### 4.3 Concurrency-safe booking gate

Inside **`booking_service.create_booking`**:

1. Validate flight exists; seat belongs to catalogue.
2. Reject duplicate **CONFIRMED** occupancy for same normalized seat (**fast path**).
3. **`reconcile_flight_inventory`**, **`flush`**.
4. If **`seats_available <= 0`** → **`NoSeatsAvailableError`** (**409**).
5. **`UPDATE flights SET seats_available = seats_available - 1`** with **`WHERE id = … AND seats_available > 0`**. **`rowcount != 1`** → **409**.
6. Insert **`Booking`** (**CONFIRMED**).
7. **`flush`**, **`reconcile_flight_inventory`**, **`commit`**.
8. **`IntegrityError`** (parallel seat grab) → full **rollback**, surface **409 SeatAlreadyHeldError**.

SQLite serializes conflicting writers on the **`flights`** row; the conditional **`UPDATE`** prevents overselling the last seat when combined with transactional rollback semantics.

---

## 5. Flight search semantics

**`flight_service.search_flights`**

- SQL filters optional **`origin`**, **`destination`** (lower-cased equality), **`departure_date`** (UTC **`[start, next day)`** window).
- Then **drops** flights where **`derive_seats_open ≤ 0`**.

Hence search results mirror “bookable from the seating chart perspective,” unlike **`GET /flights`** which lists all rows regardless of occupancy.

---

## 6. Cancellation behavior

**`booking_service.cancel_booking`**

- **404**: missing reference (`BookingNotFoundError`).
- **409**: **`BookingAlreadyCancelledError`** if status already **`CANCELLED`**.
- Otherwise set **`CANCELLED`**, **`cancelled_at`**, **`flush`**, **`reconcile_flight_inventory`**, **`commit`**.

REST exposes both **`DELETE /bookings/{ref}`** and **`POST /bookings/{ref}/cancel`**.

Frontend classifies certain **409/404** cancel responses as **informational overlays** (“Already cancelled”, “Booking not found”).

---

## 7. HTTP surface (actual paths)

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/flights` | Full schedule |
| `GET` | `/flights/search` | Filters; inventory filtered |
| `GET` | `/flights/{id}/seat-map` | Cabin tiles |
| `POST` | `/bookings` | Create → **201** |
| `GET` | `/bookings` | Query **ref** XOR **passenger_full_name** |
| `DELETE` | `/bookings/{booking_reference}` | Cancel |
| `POST` | `/bookings/{booking_reference}/cancel` | Cancel (alt) |

Swagger UI: **`/docs`**.

Domain errors mapped in **`backend/app/api/exception_handlers.py`**.

---

## 8. Frontend role

Express (`frontend/server.js`) serves static assets only. **`window.FLIGHTHUB_API_BASE`** / the **Backend base URL** field points the browser **`fetch`** at FastAPI.

**Operational note:** **`seats_available`** in JSON is already reconciled/read-side derived in **`FlightOut`** — the UI disables **Book** on **`0`** for convenience, **not** instead of backend validation.

---

## 9. Repository layout

```
backend/
  app/
    main.py               # lifespan: init_db, optional FLITHUB_RESET_SQLITE_ON_START purge
    api/deps.py           # SessionDep + booking lookup dependency
    db/session.py         # DATABASE_URL · engine · busy timeout · get_db
    domain/cabin_layout.py
    routers/flights.py
    routers/bookings.py
    services/flight_service.py
    services/booking_service.py
  scripts/                # standalone verify_*.py (temp DB each)
  tests/                  # pytest · isolated DB via module reload fixture
frontend/
  public/
  server.js
```

---

## 10. Automated testing

| Kind | Location | Purpose |
|------|-----------|---------|
| **Pytest unit/API** | `backend/tests/` | Business rules (**409** inventory, cancel restores availability, search filters); **never** imports `SessionLocal` at module scope before fixtures |
| **Script parity** | `backend/tests/test_verification_scripts.py` | Subprocess **`scripts/verify_*.py`** |

Run from **`backend/`**: `python -m pytest`.

---

## 11. Design summary

| Topic | Decision |
|-------|-----------|
| API prefix | Root **`/flights`**, **`/bookings`** (no `/api`) |
| Listed vs searched flights | **`list_flights`** all rows; **`search_flights`** only **`derive_open > 0`** |
| Public seat counts | **`FlightOut.seats_available`** from **`derive_seats_open`** |
| Persisted `seats_available` | Guarded decrement + **post-insert reconcile before commit** |
| Seat collisions | Partial unique index + transactional **`IntegrityError` → rollback** |
| Cancellation | **`reconcile_flight_inventory`** · **409** duplicate cancel |

This keeps the codebase small while mirroring inventory discipline found in larger reservation systems.
