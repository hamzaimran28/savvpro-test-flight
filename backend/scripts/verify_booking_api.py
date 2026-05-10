"""
End-to-end verification of booking APIs (isolated temp SQLite DB).

Run from `backend/`:
  python scripts/verify_booking_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

fd, dbpath = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = "sqlite:///" + dbpath.replace("\\", "/")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db.session import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.booking import Booking  # noqa: E402
from app.models.flight import Flight  # noqa: E402


def _seed_flight(total_seats: int, available: int) -> int:
    with SessionLocal() as db:
        f = Flight(
            origin="NYC",
            destination="LON",
            departure_datetime=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            duration_minutes=360,
            price_per_seat=Decimal("350.00"),
            total_seats=total_seats,
            seats_available=available,
        )
        db.add(f)
        db.commit()
        return f.id


def main() -> None:
    init_db()
    with SessionLocal() as db:
        db.execute(delete(Booking))
        db.execute(delete(Flight))
        db.commit()

    with TestClient(app) as client:
        # --- setup: 2 seats ---
        fid = _seed_flight(2, 2)

        # Create first booking
        r1 = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Ada Lovelace",
                "passport_number": "P1234567",
                "flight_id": fid,
                "seat_number": "1A",
            },
        )
        assert r1.status_code == 201, r1.text
        b1 = r1.json()
        ref1 = b1["booking_reference"]
        assert b1["booking_status"] == "CONFIRMED"
        assert b1["seat_number"] == "1A"
        assert b1["flight"]["id"] == fid
        assert b1["flight"]["seats_available"] == 1
        assert len(ref1) >= 8

        # Duplicate active seat -> 409
        r_dup = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Bob",
                "passport_number": "P7654321",
                "flight_id": fid,
                "seat_number": "1a",
            },
        )
        assert r_dup.status_code == 409

        # Second booking — other seat on a 2-seat layout (canonical 1B, not arbitrary)
        r2 = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Bob Tables",
                "passport_number": "P7654321",
                "flight_id": fid,
                "seat_number": "1B",
            },
        )
        assert r2.status_code == 201
        ref2 = r2.json()["booking_reference"]

        # Chart shows both seats on a 2-place aircraft (1A, 1B only)
        sm = client.get(f"/flights/{fid}/seat-map")
        assert sm.status_code == 200
        smj = sm.json()
        assert smj["total_seats"] == 2
        assert len(sum(smj["rows"], [])) == 2
        seats_by_label = {(t["seat_number"], t["available"]) for row in smj["rows"] for t in row}
        assert seats_by_label == {("1A", False), ("1B", False)}

        # Third booking invalid seat label -> 422
        r_bad_seat = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Carol",
                "passport_number": "P9999999",
                "flight_id": fid,
                "seat_number": "3A",
            },
        )
        assert r_bad_seat.status_code == 422

        # Unknown flight -> 404
        r_nf = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Dan",
                "passport_number": "D1111111",
                "flight_id": 99999,
                "seat_number": "9Z",
            },
        )
        assert r_nf.status_code == 404

        # Invalid passport -> 422 (FastAPI validation)
        r_bad = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Eve",
                "passport_number": "BAD-ID!",
                "flight_id": fid,
                "seat_number": "9Z",
            },
        )
        assert r_bad.status_code == 422

        # GET by reference
        g_ref = client.get("/bookings", params={"booking_reference": ref1})
        assert g_ref.status_code == 200
        assert len(g_ref.json()) == 1
        assert g_ref.json()[0]["booking_reference"] == ref1

        # GET by passenger name (case-insensitive)
        g_name = client.get("/bookings", params={"passenger_full_name": "ada lovelace"})
        assert g_name.status_code == 200
        assert len(g_name.json()) >= 1
        refs = {row["booking_reference"] for row in g_name.json()}
        assert ref1 in refs

        # Lookup validation
        assert client.get("/bookings").status_code == 422
        assert (
            client.get(
                "/bookings",
                params={"booking_reference": ref1, "passenger_full_name": "Ada"},
            ).status_code
            == 422
        )

        # DELETE cancel
        d1 = client.delete(f"/bookings/{ref1}")
        assert d1.status_code == 200
        assert d1.json()["booking_status"] == "CANCELLED"
        assert d1.json()["cancelled_at"] is not None

        # Second cancel -> 409
        assert client.delete(f"/bookings/{ref1}").status_code == 409

        # POST cancel endpoint on ref2
        pc = client.post(f"/bookings/{ref2}/cancel")
        assert pc.status_code == 200
        assert pc.json()["booking_status"] == "CANCELLED"

        # Re-book freed seats (partial unique + inventory restored)
        r_after = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Frank",
                "passport_number": "F2222222",
                "flight_id": fid,
                "seat_number": "1A",
            },
        )
        assert r_after.status_code == 201
        ref_f = r_after.json()["booking_reference"]

        r_after_b = client.post(
            "/bookings",
            json={
                "passenger_full_name": "Grace",
                "passport_number": "G3333333",
                "flight_id": fid,
                "seat_number": "1B",
            },
        )
        assert r_after_b.status_code == 201

        # Full cabin — attempted duplicate-confirmed seat
        assert (
            client.post(
                "/bookings",
                json={
                    "passenger_full_name": "Heidi",
                    "passport_number": "H4444444",
                    "flight_id": fid,
                    "seat_number": "1B",
                },
            ).status_code
            == 409
        )

        g_f = client.get("/bookings", params={"booking_reference": ref_f})
        assert g_f.status_code == 200
        assert len(g_f.json()) == 1

        # Sequential last-seat contention: decrement path only allows one winner
        with SessionLocal() as db:
            db.execute(delete(Booking))
            db.execute(delete(Flight))
            db.commit()
        fid_one = _seed_flight(1, 1)
        ok_a = client.post(
            "/bookings",
            json={
                "passenger_full_name": "A",
                "passport_number": "A1111111",
                "flight_id": fid_one,
                "seat_number": "1A",
            },
        )
        assert ok_a.status_code == 201
        lose = client.post(
            "/bookings",
            json={
                "passenger_full_name": "B",
                "passport_number": "B2222222",
                "flight_id": fid_one,
                "seat_number": "1A",
            },
        )
        assert lose.status_code == 409

        # Cancel unknown ref -> 404
        assert client.delete("/bookings/does-not-exist-ref").status_code == 404
        assert client.post("/bookings/does-not-exist-ref/cancel").status_code == 404

    engine.dispose()
    try:
        os.unlink(dbpath)
    except OSError:
        pass

    print("All booking API verification checks passed.")


if __name__ == "__main__":
    main()
