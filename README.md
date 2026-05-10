# FlightHub

Internal **flight search and booking console** for agency staff: browse the schedule, filter flights, book a seat with passenger details, look up reservations, and cancel them. The backend is **FastAPI + SQLite**; the staff UI is **static HTML/CSS/JavaScript** served by **Express**.

---

## Project overview

| Layer | Role |
|--------|------|
| **Backend** (`backend/`) | REST API, transactional inventory, deterministic seat map, domain validation |
| **Frontend** (`frontend/`) | FlightHub dashboard (search, table, booking form, cabin map, lookup, cancel) |
| **Database** | SQLite file (default `./flighthub.db` when uvicorn runs from `backend/`) |

There is **no** `/api` prefix: routes are rooted at **`/flights`** and **`/bookings`**.

---

## Prerequisites

- **Python** 3.10+ recommended  
- **Node.js** 18+ (for the static UI server)

---

## Dependency installation

### Backend

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Optional (tests + scripts):

```bash
pip install -r requirements-dev.txt
```

### Frontend

```bash
cd frontend
npm install
```

---

## Run locally (clean clone)

Use **two terminals**: API first, then UI.

### Backend (FastAPI)

From `backend/`:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000`
- Interactive docs: `http://127.0.0.1:8000/docs`

### Frontend (Express static server)

From `frontend/`:

```bash
npm start
```

- UI: `http://127.0.0.1:3000` (override with `PORT=8080 npm start` if needed)

In the UI header, **Backend base URL** defaults to `http://127.0.0.1:8000`. Click **Test connection** to verify CORS and reachability.

**CORS** is restricted to `http://127.0.0.1:3000` and `http://localhost:3000`; use one of those origins or extend `backend/app/main.py`.

---

## Tests

From `backend/`:

```bash
python -m pytest
```

Runs isolated SQLite per test (`tests/conftest.py`) and subprocess checks for `scripts/verify_*.py`. See **`requirements-dev.txt`** for pytest.

Optional one-off verification (each script uses its own temp DB):

```bash
cd backend
python scripts/verify_flight_api.py
python scripts/verify_booking_api.py
python scripts/verify_overbooking_concurrency.py
```

---

## Documentation

| File | Contents |
|------|-----------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System design: inventory, concurrency, cancellations, layering |
| [`USER_GUIDE.md`](USER_GUIDE.md) | How to use the UI and **`curl`** examples for every endpoint |
| [`AI_USAGE.md`](AI_USAGE.md) | How AI-assisted development was used on this project |
| [`TASK.md`](TASK.md) | Original assessment requirements (if applicable) |

---

## Assumptions and design notes

1. **Trust boundary**: No authentication is implemented; FlightHub is an internal operator tool.
2. **Time zones**: **`departure_date`** filters use **UTC** calendar-day bounds; timestamps are timezone-aware (`departure_datetime`).
3. **Inventory truth**: Responses expose **`seats_available`** derived from **confirmed occupancy** on the canonical seat catalogue (aligned with **`GET /flights/{id}/seat-map`**), not naive row counts alone.
4. **Concurrency**: Last-seat safety uses a **conditional `UPDATE`** on `Flight.seats_available`; after a successful booking insert, **`reconcile_flight_inventory`** keeps the persisted column aligned with derived open seats.
5. **Cancellation**: Second cancel on the same reference returns **HTTP 409** (`BookingAlreadyCancelledError`); the UI treats that as informational.
6. **SQLite**: Engine uses `check_same_thread=False` and a **busy timeout** for writer contention; see `app/db/session.py`.
7. **Optional reset**: Set `FLITHUB_RESET_SQLITE_ON_START=1` to wipe flights and bookings on API startup (development only).

---

## Repository layout

```
savvpro-test-flight/
├── backend/
│   ├── app/                 # FastAPI application
│   ├── scripts/             # Standalone verification scripts
│   ├── tests/               # pytest suite
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── public/              # index.html, css/, js/
│   ├── server.js
│   └── package.json
├── ARCHITECTURE.md
├── USER_GUIDE.md
├── AI_USAGE.md
└── README.md
```

---

## Assessment / submission

If you are completing a hiring task, follow the fork / branch instructions in your assignment (see legacy steps in your fork’s history or **`TASK.md`**). This README is the primary **project** documentation for running and understanding FlightHub.
