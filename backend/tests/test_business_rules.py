"""Business-rules + API correctness (isolated DB per test via ``client`` fixture)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.flight import Flight


def _session_local():
    """Bind after ``client`` fixture reloads ``app.db.session`` (no module-level import)."""
    from app.db.session import SessionLocal

    return SessionLocal


def test_booking_conflict_when_flight_is_full_single_seat(client: TestClient) -> None:
    """
    Rule: no overlapping confirmed reservations — with one cabin position, the
    second reservation attempt must fail with HTTP 409.
    """
    with _session_local()() as db:
        row = Flight(
            origin="INV",
            destination="ORY",
            departure_datetime=datetime(2027, 1, 15, 8, 0, tzinfo=timezone.utc),
            duration_minutes=90,
            price_per_seat=Decimal("220.00"),
            total_seats=1,
            seats_available=1,
        )
        db.add(row)
        db.commit()
        flight_id = row.id

    first = client.post(
        "/bookings",
        json={
            "passenger_full_name": "First Traveller",
            "passport_number": "AA1111222",
            "flight_id": flight_id,
            "seat_number": "1A",
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/bookings",
        json={
            "passenger_full_name": "Second Traveller",
            "passport_number": "BB3333444",
            "flight_id": flight_id,
            "seat_number": "1A",
        },
    )
    assert second.status_code == 409, second.text
    detail = second.json().get("detail", "")
    assert isinstance(detail, str)
    lower = detail.lower()
    assert "seat" in lower or "no seats" in lower or "occupied" in lower or "reserved" in lower


def test_cancel_booking_marks_cancelled_and_restores_inventory(client: TestClient) -> None:
    """Cancellation flips status and frees capacity so list APIs show full inventory."""
    with _session_local()() as db:
        row = Flight(
            origin="ZRH",
            destination="HAM",
            departure_datetime=datetime(2027, 2, 1, 14, 30, tzinfo=timezone.utc),
            duration_minutes=75,
            price_per_seat=Decimal("180.00"),
            total_seats=2,
            seats_available=2,
        )
        db.add(row)
        db.commit()
        flight_id = row.id

    book = client.post(
        "/bookings",
        json={
            "passenger_full_name": "Ada Test",
            "passport_number": "CX9999888",
            "flight_id": flight_id,
            "seat_number": "1A",
        },
    )
    assert book.status_code == 201, book.text
    reference = book.json()["booking_reference"]

    before_rows = client.get("/flights").json()
    before = next(f for f in before_rows if f["id"] == flight_id)
    assert before["seats_available"] == 1

    cancel_res = client.delete(f"/bookings/{reference}")
    assert cancel_res.status_code == 200, cancel_res.text
    cancelled = cancel_res.json()
    assert cancelled["booking_status"] == "CANCELLED"
    assert cancelled["cancelled_at"] is not None

    after_rows = client.get("/flights").json()
    after = next(f for f in after_rows if f["id"] == flight_id)
    assert after["seats_available"] == 2


def test_flight_search_filters_match_schedule(client: TestClient) -> None:
    """
    Search must honour origin / destination / departure_date and only return flights
    with positive derived inventory (consistent with flight_service.search_flights).
    """
    with _session_local()() as db:
        db.add_all(
            [
                Flight(
                    origin="NYC",
                    destination="LON",
                    departure_datetime=datetime(
                        2026, 7, 1, 10, 0, tzinfo=timezone.utc
                    ),
                    duration_minutes=400,
                    price_per_seat=Decimal("500.00"),
                    total_seats=10,
                    seats_available=10,
                ),
                Flight(
                    origin="NYC",
                    destination="PAR",
                    departure_datetime=datetime(
                        2026, 7, 2, 12, 0, tzinfo=timezone.utc
                    ),
                    duration_minutes=480,
                    price_per_seat=Decimal("450.00"),
                    total_seats=20,
                    seats_available=20,
                ),
                Flight(
                    origin="SFO",
                    destination="NYC",
                    departure_datetime=datetime(
                        2026, 7, 2, 23, 30, tzinfo=timezone.utc
                    ),
                    duration_minutes=360,
                    price_per_seat=Decimal("300.00"),
                    total_seats=50,
                    seats_available=50,
                ),
            ],
        )
        db.commit()

    full = client.get("/flights")
    assert full.status_code == 200
    rows = full.json()
    assert len(rows) == 3
    par_row = next(r for r in rows if r["destination"] == "PAR")

    narrowed = client.get(
        "/flights/search",
        params={"origin": "nyc", "destination": "par"},
    )
    assert narrowed.status_code == 200
    nj = narrowed.json()
    assert len(nj) == 1
    assert nj[0]["id"] == par_row["id"]

    jul2 = client.get("/flights/search", params={"departure_date": "2026-07-02"})
    assert jul2.status_code == 200
    assert len(jul2.json()) == 2

    jul1 = client.get("/flights/search", params={"departure_date": "2026-07-01"})
    assert len(jul1.json()) == 1
    assert jul1.json()[0]["destination"] == "LON"
