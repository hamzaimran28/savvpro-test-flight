"""
Verify that overbooking cannot occur: atomic ``seats_available`` decrement + transactional rollback.

Runs concurrent ``create_booking`` calls (each with its own DB session/thread) against a shared
SQLite file and asserts inventory invariants held after contention.

Usage (from ``backend/``):
  python scripts/verify_overbooking_concurrency.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

fd, dbpath = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = "sqlite:///" + dbpath.replace("\\", "/")

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal, engine, init_db  # noqa: E402
from app.exceptions import NoSeatsAvailableError, SeatAlreadyHeldError  # noqa: E402
from app.models.booking import Booking, BookingStatus  # noqa: E402
from app.models.flight import Flight  # noqa: E402
from app.services import booking_service  # noqa: E402


def _assert_inventory(db: Session, flight_id: int) -> None:
    flight = db.get(Flight, flight_id)
    assert flight is not None
    confirmed = db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.flight_id == flight_id,
            Booking.booking_status == BookingStatus.CONFIRMED,
        ),
    )
    assert confirmed is not None
    expected = flight.total_seats - int(confirmed)
    assert flight.seats_available == expected, (
        f"Invariant broken: seats_available={flight.seats_available} "
        f"but total_seats={flight.total_seats} - confirmed={confirmed} => expected {expected}"
    )
    assert 0 <= flight.seats_available <= flight.total_seats


def _reset(db: Session) -> None:
    db.execute(delete(Booking))
    db.execute(delete(Flight))
    db.commit()


def _seed_flight(db: Session, *, total: int, available: int) -> int:
    f = Flight(
        origin="TST",
        destination="ZZZ",
        departure_datetime=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        duration_minutes=60,
        price_per_seat=Decimal("100.00"),
        total_seats=total,
        seats_available=available,
    )
    db.add(f)
    db.commit()
    return f.id


def _try_book(
    flight_id: int,
    worker_id: int,
    seat: str,
    barrier: threading.Barrier | None,
) -> tuple[str, str | None]:
    """Returns (\"ok\"|\"no_seat\"|\"seat_held\"|\"error\", detail)."""
    if barrier is not None:
        barrier.wait()
    db = SessionLocal()
    try:
        booking_service.create_booking(
            db,
            flight_id=flight_id,
            passenger_full_name=f"Passenger {worker_id}",
            passport_number=f"W{worker_id % 10000000:07d}",
            seat_number=seat,
        )
        return ("ok", None)
    except NoSeatsAvailableError:
        db.rollback()
        return ("no_seat", None)
    except SeatAlreadyHeldError:
        db.rollback()
        return ("seat_held", None)
    except Exception:
        db.rollback()
        return ("error", traceback.format_exc())
    finally:
        db.close()


def run_scenario(
    *,
    name: str,
    total_seats: int,
    workers: int,
    seat_fn: int,
    barrier: bool,
) -> None:
    """
    seat_fn(i) -> seat label for worker i.
    """
    init_db()
    with SessionLocal() as db:
        _reset(db)
        fid = _seed_flight(db, total=total_seats, available=total_seats)

    b = threading.Barrier(workers) if barrier and workers > 0 else None

    ok = no_seat = seat_held = err = 0
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=max(8, workers)) as ex:
        futs = [
            ex.submit(
                _try_book,
                fid,
                i,
                f"{seat_fn(i)}",
                b,
            )
            for i in range(workers)
        ]
        for fut in as_completed(futs):
            kind, detail = fut.result()
            if kind == "ok":
                ok += 1
            elif kind == "no_seat":
                no_seat += 1
            elif kind == "seat_held":
                seat_held += 1
            else:
                err += 1
                if detail:
                    errors.append(detail)

    with SessionLocal() as db:
        _assert_inventory(db, fid)
        flight = db.get(Flight, fid)
        assert flight is not None
        confirmed = db.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.flight_id == fid,
                Booking.booking_status == BookingStatus.CONFIRMED,
            ),
        )
        assert confirmed == ok, f"{name}: ok count {ok} != confirmed rows {confirmed}"
        assert ok + no_seat + seat_held + err == workers
        assert err == 0, f"{name}: worker errors\n" + "\n".join(errors)
        assert ok <= total_seats, f"{name}: more successes {ok} than capacity {total_seats}"

    print(f"  [{name}] workers={workers} successes={ok} no_seat={no_seat} seat_held={seat_held} final_avail={flight.seats_available}")


def main() -> None:
    print("Overbooking / transactional inventory verification (concurrent SQLite)")

    # Many threads, one seat: at most one success
    run_scenario(
        name="last-seat stampede (unique seats, capacity 1)",
        total_seats=1,
        workers=40,
        seat_fn=lambda i: f"R{i}",
        barrier=True,
    )

    # Same physical seat label for everyone on a single-seat flight
    run_scenario(
        name="last-seat stampede (all same seat label)",
        total_seats=1,
        workers=40,
        seat_fn=lambda i: "1A",
        barrier=True,
    )

    # Capacity 5, 25 workers with distinct seats -> exactly 5 successes
    run_scenario(
        name="capacity 5 vs 25 distinct seats",
        total_seats=5,
        workers=25,
        seat_fn=lambda i: f"S{i}",
        barrier=True,
    )

    # Many threads fight for the same seat while several seats exist: only one holder for that seat
    run_scenario(
        name="same hot seat with spare capacity elsewhere",
        total_seats=8,
        workers=24,
        seat_fn=lambda i: "1A" if i % 2 == 0 else f"H{i}",
        barrier=True,
    )

    # Repeat last-seat scenario without barrier (ordering still serializes writes; invariant must hold)
    run_scenario(
        name="last-seat no barrier",
        total_seats=1,
        workers=30,
        seat_fn=lambda i: f"N{i}",
        barrier=False,
    )

    engine.dispose()
    try:
        os.unlink(dbpath)
    except OSError:
        pass

    print("All overbooking / transactional checks passed.")


if __name__ == "__main__":
    main()
