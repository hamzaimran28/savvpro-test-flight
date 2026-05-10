"""One-off verification script for flight endpoints (temp SQLite DB). Run from `backend/`: python scripts/verify_flight_api.py"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure `backend/` is on sys.path when running as `python scripts/verify_flight_api.py`
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
from datetime import datetime, timezone
from decimal import Decimal

fd, dbpath = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = "sqlite:///" + dbpath.replace("\\", "/")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db.session import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.flight import Flight  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        db.execute(delete(Flight))
        db.commit()
        db.add_all(
            [
                Flight(
                    origin="NYC",
                    destination="LON",
                    departure_datetime=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
                    duration_minutes=400,
                    price_per_seat=Decimal("500.00"),
                    total_seats=10,
                    seats_available=0,
                ),
                Flight(
                    origin="NYC",
                    destination="PAR",
                    departure_datetime=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
                    duration_minutes=480,
                    price_per_seat=Decimal("450.00"),
                    total_seats=20,
                    seats_available=3,
                ),
                Flight(
                    origin="SFO",
                    destination="NYC",
                    departure_datetime=datetime(2026, 7, 2, 23, 30, tzinfo=timezone.utc),
                    duration_minutes=360,
                    price_per_seat=Decimal("300.00"),
                    total_seats=50,
                    seats_available=1,
                ),
            ]
        )
        db.commit()

    with TestClient(app) as client:
        r = client.get("/flights")
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 3
        assert [x["destination"] for x in data] == ["LON", "PAR", "NYC"]
        assert data[0]["seats_available"] == 0
        need = {
            "id",
            "origin",
            "destination",
            "departure_datetime",
            "duration_minutes",
            "price_per_seat",
            "total_seats",
            "seats_available",
            "created_at",
        }
        assert need <= set(data[0].keys())

        r2 = client.get("/flights/search")
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2) == 2
        assert {x["destination"] for x in d2} == {"PAR", "NYC"}

        r3 = client.get("/flights/search", params={"origin": "nyc", "destination": "par"})
        assert r3.status_code == 200
        assert len(r3.json()) == 1 and r3.json()[0]["id"] == data[1]["id"]

        r4 = client.get("/flights/search", params={"departure_date": "2026-07-02"})
        assert r4.status_code == 200
        assert len(r4.json()) == 2

        r5 = client.get("/flights/search", params={"departure_date": "2026-07-01"})
        assert len(r5.json()) == 0

        r6 = client.get("/flights/search", params={"departure_date": "bad"})
        assert r6.status_code == 422

        assert client.get("/flights/nope").status_code == 404

    engine.dispose()
    try:
        os.unlink(dbpath)
    except OSError:
        pass
    print("All flight API checks passed.")


if __name__ == "__main__":
    main()
