# FlightHub — System Architecture

This document describes the complete system design, data model, API, concurrency model, and project layout for **FlightHub**: an internal flight search and booking tool. It guides implementation; it does not include application source code.

---

## 1. Goals and scope

FlightHub allows agency staff to:

- Browse and search available flights.
- Create confirmed bookings (passenger details + seat selection).
- Look up bookings by passenger name or booking reference.
- Cancel bookings and return seats to inventory.

**Out of scope:** payments, external airline APIs, authentication (internal trust boundary assumed unless extended later), **waitlists**, and **any capacity above physical seat count**.

**Stack:** **FastAPI + SQLite** (backend); **Express** serving **plain HTML/CSS/JavaScript** (frontend). All services run locally.

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (HTML/CSS/JS served by Express)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP/JSON (REST)
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI application                                         │
│  • routers  → HTTP mapping, validation, status codes        │
│  • services → booking rules, inventory, transactions        │
│  • models/schemas → persistence and request/response shapes  │
│  • database → SQLAlchemy (or equivalent) + SQLite         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  SQLite (single file) — flights, bookings                    │
└─────────────────────────────────────────────────────────────┘
```

The browser **does not** access SQLite directly. Express **serves static assets**; the browser calls the FastAPI backend for all business operations.

---

## 3. Core entities

### 3.1 Flight

| Field | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Surrogate primary key. |
| `origin` | String | Departure city or airport code (consistent format in the app). |
| `destination` | String | Arrival city or airport code. |
| `departure_datetime` | DateTime (UTC recommended) | Scheduled departure instant. |
| `duration` | Integer | Duration in **minutes** (non-negative). |
| `price_per_seat` | Decimal | Price per seat in one logical currency. |
| `total_seats` | Integer | Physical seat count; immutable after row creation. |
| `seats_available` | Integer | Remaining sellable seats; **must** satisfy `0 ≤ seats_available ≤ total_seats` at every commit. |

**Invariants:**

- `total_seats` does not change for the lifetime of the flight row.
- `seats_available` is the **authoritative** count for how many additional **confirmed** bookings may still be created.

### 3.2 Booking

| Field | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Surrogate primary key. |
| `booking_reference` | String (unique) | Opaque, server-generated identifier; never reused. |
| `flight_id` | Integer (FK → Flight) | Target flight. |
| `passenger_full_name` | String | Required for lookup and records. |
| `passport_number` | String | Required; format rules validated at API boundary. |
| `seat_number` | String | Passenger-selected label (e.g. `12A`); uniqueness among **active** bookings per flight (see §5). |
| `booking_status` | Enum | **`CONFIRMED`** or **`CANCELLED`**. |
| `created_at` | DateTime (UTC) | Booking creation timestamp. |

**Optional (audit clarity):** `cancelled_at` (nullable) when status is `CANCELLED`.

**Invariants:**

- Each **CONFIRMED** booking corresponds to **exactly one** unit of inventory reserved on the flight (§4).
- **CONFIRMED → CANCELLED** restores **one** seat to `seats_available` in the same transaction.
- Two **active** (CONFIRMED) bookings on the same flight **cannot** share the same `seat_number`.

---

## 4. Seat inventory and concurrency

### 4.1 How inventory is represented

- **`total_seats`** — capacity for reporting and UI.
- **`seats_available`** — how many more **confirmed** bookings the system may accept.

Relationship (post-migration, ignoring corruption):  
`confirmed_bookings_count = total_seats - seats_available` for each flight.

### 4.2 Policy: no waitlists, no overbooking

- **Waitlists are not implemented.**
- **Overbooking is not allowed** — no capacity beyond `total_seats`.
- When there is **no** remaining inventory (including the case where the **last** seat was just taken by another request), the booking attempt **must fail with HTTP 409 Conflict**.

### 4.3 Atomic inventory update (prevents overselling)

Booking creation **must** run inside a **single database transaction** using this pattern:

1. Validate that the flight exists (and any bookability rule, e.g. not in the past — if adopted, document in README).
2. **Atomically decrement** stock with one `UPDATE` that applies **only if** seats remain:

   - Update `Flight` so `seats_available` becomes `seats_available - 1`  
     **where** `id = :flight_id` **and** `seats_available > 0`.

3. Check **rows affected** (or equivalent):

   - **One row updated** — reservation succeeded; insert the `Booking` with `booking_status = CONFIRMED` and commit (after seat uniqueness check / insert — §5).
   - **Zero rows updated** — flight was already full or lost a race for the last seat; **do not** insert a booking; roll back; respond **409 Conflict** with a clear `detail` message.

4. Seat uniqueness for active bookings (§5) is enforced **before commit**, typically via a **partial unique index** so cancelled rows do not block reuse.

**Why this prevents overselling**

The classic last-seat bug is: two requests **read** `seats_available = 1`, both decide to book, and both **write**, selling two seats for one. Here the **read and conditional write are one atomic statement** on the `Flight` row. SQLite serializes conflicting **writes** to the same row. So:

- The first transaction’s conditional `UPDATE` succeeds (`1 → 0`).
- The second transaction’s conditional `UPDATE` sees `seats_available = 0` and updates **zero** rows.

Thus **at most one** confirmation can pass the inventory gate per last seat, without application-level mutexes beyond the database.

**HTTP:** inventory failure or last-seat race → **409 Conflict** (valid request, current state does not allow the operation).

### 4.4 Cancellation and inventory

In one transaction:

- Load booking by **booking reference**; require `booking_status = CONFIRMED`.
- Set `booking_status = CANCELLED` (and `cancelled_at` if used).
- `UPDATE Flight` set `seats_available = seats_available + 1` with a safety check such as `seats_available < total_seats` to avoid overshooting if data were inconsistent.

**Idempotency:** define behavior for “cancel again” (e.g. **409** if already **CANCELLED**) and document it in the API section and README.

### 4.5 SQLite practice

Concurrent writers may hit **`SQLITE_BUSY`**. Setting a **busy timeout** on the engine/connection reduces transient failures; document the value in README.

---

## 5. Seat assignment rules

### 5.1 Passenger selects seat

The client sends `seat_number` as a string. The server validates (length, allowed characters) as needed.

### 5.2 No shared seat among active bookings

Two **CONFIRMED** bookings on the **same flight** **cannot** use the same `seat_number`.

### 5.3 Cancelled bookings free the seat for reuse

A **naive** `UNIQUE(flight_id, seat_number)` on all rows would **prevent** rebooking the same seat label after cancellation, because the cancelled row still holds `(flight_id, seat_number)`.

**Recommended:** a **partial unique index** in SQLite, e.g. unique on `(flight_id, seat_number)` **where** `booking_status = 'CONFIRMED'`.

Effects:

- **CONFIRMED** bookings cannot duplicate a seat on the same flight.
- **CANCELLED** rows are excluded from the index, so a **new** **CONFIRMED** booking may reuse that seat.

### 5.4 Transaction order and rollback

1. Conditional decrement of `seats_available`.
2. Insert **Booking** (`CONFIRMED`).

If the insert fails on unique violation (another worker confirmed the same seat in a narrow race), **roll back the entire transaction** — including the decrement — so inventory and seats stay consistent. Return **409 Conflict** with an appropriate message (seat no longer available).

---

## 6. API design

Use a stable prefix such as `/api` (document final URLs in README).

### 6.1 List flights

| Item | Specification |
|------|----------------|
| **Endpoint** | `GET /api/flights` |
| **Purpose** | Return **all** flights for browsing. |
| **Response** | `200 OK` — array of flights: `id`, `origin`, `destination`, `departure_datetime`, `duration`, `price_per_seat`, `total_seats`, `seats_available`. |
| **Empty** | `200 OK` with `[]`. |

### 6.2 Search flights

| Item | Specification |
|------|----------------|
| **Endpoint** | `GET /api/flights/search` (alternatively `GET /api/flights` with filters only — pick one approach and document it). |
| **Query params** | e.g. `origin`, `destination`, `departure_date` (compare **date** part to `departure_datetime` using a **defined** timezone policy — **UTC** recommended). |
| **Response** | `200 OK` — filtered flights; `[]` if no matches. |
| **Errors** | `422 Unprocessable Entity` for invalid or malformed parameters. |

### 6.3 Create booking

| Item | Specification |
|------|----------------|
| **Endpoint** | `POST /api/bookings` |
| **Body** | `flight_id`, `passenger_full_name`, `passport_number`, `seat_number` |
| **Success** | `201 Created` — include `booking_reference`, `booking_status`, flight summary, seat, `created_at`. |
| **Errors** | `422` validation; `404` flight not found; **`409 Conflict`** — no seats, seat taken, or inventory race; optional `409`/`422` for “departure in the past” if that rule exists. |

### 6.4 Lookup bookings

| Item | Specification |
|------|----------------|
| **Endpoint** | `GET /api/bookings` |
| **Query** | `booking_reference` **or** `passenger_full_name` (exact vs case-insensitive — **document**). |
| **Response** | `200 OK` — list of bookings, each showing **booking reference**, **flight details**, **passenger name**, **seat number**, **booking status**. |
| **No match** | `200 OK` + `[]` **or** `404` when a specific reference must exist — **choose and document**. |

### 6.5 Cancel booking

| Item | Specification |
|------|----------------|
| **Endpoint** | `DELETE /api/bookings/{booking_reference}` or `POST /api/bookings/{booking_reference}/cancel` |
| **Purpose** | Cancel **using booking reference** (required by product). |
| **Success** | `200 OK` (body with updated booking) or `204 No Content` |
| **Errors** | `404` unknown reference; **`409`** if already **CANCELLED** (recommended). |

---

## 7. HTTP status summary

| Situation | Code |
|-----------|------|
| Successful read / search | `200` |
| Booking created | `201` |
| Validation failure | `422` |
| Unknown flight or booking | `404` |
| No inventory, seat conflict, duplicate cancel | **`409 Conflict`** |

---

## 8. Recommended project structure

### 8.1 Backend (FastAPI)

```
/backend
  /app
    main.py                    # App factory, router mount, CORS, lifespan
    /database
      session.py               # Engine, session factory, get_db
      base.py                  # Declarative base (if using SQLAlchemy)
    /models
      flight.py
      booking.py
    /schemas
      flight.py                # Pydantic request/response models
      booking.py
    /routers
      flights.py
      bookings.py
    /services
      flight_service.py        # List + search (read queries)
      booking_service.py       # Create/cancel, transactions, inventory rules
  requirements.txt
```

### 8.2 Frontend (Express)

```
/frontend
  server.js                    # express.static, port
  /public
    index.html
    /css
    /js
  package.json
```

### 8.3 Tests

```
/tests
  …                            # pytest: API or service-level tests
```

Use a **dedicated SQLite** file or in-memory DB for tests; reset schema/data per test or per class for isolation.

---

## 9. Why business logic belongs in **services**, not **route handlers**

| Responsibility | Routers (handlers) | Services |
|----------------|-------------------|----------|
| Map HTTP path/method to code | ✓ | |
| Parse and validate input (Pydantic, query params) | ✓ | |
| Choose HTTP status and response body | ✓ | |
| **Start/commit/rollback database transactions** | | ✓ |
| **Enforce inventory rules** (conditional update, 409 semantics) | | ✓ |
| **Enforce seat uniqueness policy** with ORM/DB | | ✓ |
| **Cancellation + seat restoration** atomically | | ✓ |
| **Reusable** from future CLIs, jobs, or tests without HTTP | | ✓ |

**Route handlers should stay thin:** validate → call **one** service method → return result or map a domain/service exception to **404** / **409** / **422**.  

If booking rules live in routers, the same rules get **duplicated** or **skipped** when adding another entry point, and **unit testing** business rules without HTTP becomes painful. **Services** are the single place where **“create booking safely”** and **“cancel booking with inventory fix”** are defined — which is essential for correctness under concurrency and for the **business-rule tests** the product requires.

---

## 10. Frontend role

Express serves static HTML/CSS/JS. The UI may disable “Book” when `seats_available === 0`, but **all guarantees** are enforced by the backend.

---

## 11. Design decisions (summary)

| Topic | Decision |
|-------|-----------|
| Inventory | `seats_available` on `Flight`; only changed in transactional booking/cancel flows. |
| Overbooking / waitlist | **Not allowed**; **no waitlists**; failure → **409**. |
| Concurrency | Conditional single-row `UPDATE` + rows-affected check; transaction wraps booking insert. |
| Seat reuse after cancel | **Partial unique index** on `(flight_id, seat_number)` for **CONFIRMED** only. |
| Layers | **Services** own transactions and rules; **routers** expose HTTP only. |

This architecture stays small but is **production-shaped**: clear boundaries, an explicit concurrency story, and REST semantics aligned with real inventory systems.
