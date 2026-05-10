# FlightHub

Flight search and booking for internal staff: browse schedules, filter bookable flights, reserve seats with passenger details, look up reservations, and cancel them.

---

## Tech stack

| Layer | Details |
|-------|---------|
| Backend | FastAPI · SQLAlchemy · SQLite (`backend/app/`) |
| Frontend | HTML, CSS, JS — static files via Express (`frontend/public/`) |
| API | REST JSON (`/flights`, `/bookings`; no `/api` prefix) |

Deeper design (inventory, transactions, layering) lives in **`ARCHITECTURE.md`**.

---

## Quick start (~2 terminals)

**Prerequisites:** Python 3.10+, Node.js 18+.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt   # optional — for pytest
```

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

| | URL |
|--|-----|
| API | http://127.0.0.1:8000 |
| Swagger | http://127.0.0.1:8000/docs |

### 2. Frontend

```bash
cd frontend
npm install
npm start
```

| | URL |
|--|-----|
| UI | http://127.0.0.1:3000 |

Set **Backend base URL** in the header to `http://127.0.0.1:8000` (default). Use **Test connection** once the API is up. CORS allows `localhost:3000` and `127.0.0.1:3000` only — see `backend/app/main.py` if you need another origin.

---

## Tests

```bash
cd backend
python -m pytest
```

Optional smoke scripts (each uses a temporary SQLite file):

```bash
python scripts/verify_flight_api.py
python scripts/verify_booking_api.py
python scripts/verify_overbooking_concurrency.py
```

---

## Assumptions (brief)

- **No auth** — internal-trust boundary.
- **Search date filter** uses **UTC calendar day** bounds.
- **`FLITHUB_RESET_SQLITE_ON_START`** (see `backend/app/main.py`) can wipe DB on startup — dev only.

For inventory rules, cancellation semantics, and concurrency, see **`ARCHITECTURE.md`**.

---

## Project structure

```
backend/          FastAPI app, pytest, verification scripts
frontend/         Express static server + public UI
USER_GUIDE.md     How to use the UI + sample curl
ARCHITECTURE.md   Technical design
AI_USAGE.md       AI-assisted development disclosure
TASK.md           Original assessment brief (if applicable)
```

Assessment submission mechanics (fork/branch): follow **`TASK.md`** or your recruiter’s instructions.
