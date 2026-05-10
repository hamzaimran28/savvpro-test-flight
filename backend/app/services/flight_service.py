"""Flight listing and search (read-side query logic only)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.cabin_layout import (
    CANON_COLUMNS_PER_ROW,
    canonical_seat_labels,
    normalize_seat_code,
    row_number_from_label,
)
from app.exceptions import FlightNotFoundError
from app.models.booking import Booking, BookingStatus
from app.models.flight import Flight
from app.schemas.flight import FlightOut, FlightSearchQuery, SeatMapOut, SeatMapTile


def canonical_positions_with_confirmed_booking(session: Session, flight: Flight) -> frozenset[str]:
    """
    Normalized occupied **chart** seats: matches how ``SeatMapTile.available`` is built.

    ``COUNT(CONFIRMED)`` can diverge when legacy rows collide on the same physical seat after
    ``normalize_seat_code`` — the diagram only hides one tile per canonical code.
    """

    catalogue = frozenset(canonical_seat_labels(flight.total_seats))
    raw_seats = session.scalars(
        select(Booking.seat_number).where(
            Booking.flight_id == flight.id,
            Booking.booking_status == BookingStatus.CONFIRMED,
        ),
    ).all()
    normalized = {normalize_seat_code(str(s)) for s in raw_seats}
    return frozenset(normalized & catalogue)


def derive_seats_open(session: Session, flight: Flight) -> int:
    """
    Open-seat count identical to **`sum(tile.available)** on GET /seat-map** (distinct occupied
    positions on this aircraft catalogue).
    Persisted ``Flight.seats_available`` should be reconciled to this after writes.
    """

    taken = canonical_positions_with_confirmed_booking(session, flight)
    return max(0, flight.total_seats - len(taken))


def purge_all_bookings_and_flights(session: Session) -> None:
    """Development helper: truncate schedule + reservations."""

    session.execute(delete(Booking))
    session.execute(delete(Flight))
    session.commit()


def reconcile_flight_inventory(session: Session, flight: Flight) -> None:
    """Align persisted ``Flight.seats_available`` with confirmed booking rows."""

    flight.seats_available = derive_seats_open(session, flight)


def flight_as_out(session: Session, flight: Flight) -> FlightOut:
    """Public API flight row; ``seats_available`` mirrors the seat-map / booking truth (read-only)."""

    return FlightOut(
        id=flight.id,
        origin=flight.origin,
        destination=flight.destination,
        departure_datetime=flight.departure_datetime,
        duration_minutes=flight.duration_minutes,
        price_per_seat=flight.price_per_seat,
        total_seats=flight.total_seats,
        seats_available=derive_seats_open(session, flight),
        created_at=flight.created_at,
    )


def list_flights(session: Session) -> list[Flight]:
    """Return every flight, soonest departure first."""
    stmt = select(Flight).order_by(Flight.departure_datetime.asc())
    return list(session.scalars(stmt).all())


def search_flights(session: Session, filters: FlightSearchQuery) -> list[Flight]:
    """
    Find flights matching optional criteria.

    “Has inventory” matches **seat-map derivation** ``derive_seats_open`` (distinct occupied
    positions), not ``COUNT(CONFIRMED)``.
    Origin and destination comparisons are case-insensitive when provided.
    Departure filters use the UTC calendar day of ``flight.departure_datetime``.
    """
    stmt = select(Flight)

    if filters.origin:
        needle = filters.origin.lower()
        stmt = stmt.where(func.lower(Flight.origin) == needle)

    if filters.destination:
        needle = filters.destination.lower()
        stmt = stmt.where(func.lower(Flight.destination) == needle)

    if filters.departure_date is not None:
        day_start = datetime.combine(filters.departure_date, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        stmt = stmt.where(
            Flight.departure_datetime >= day_start,
            Flight.departure_datetime < day_end,
        )

    stmt = stmt.order_by(Flight.departure_datetime.asc())
    candidates = list(session.scalars(stmt).all())
    return [f for f in candidates if derive_seats_open(session, f) > 0]


def seat_map_for_flight(session: Session, flight_id: int) -> SeatMapOut:
    """Seat chart with occupation derived from CONFIRMED bookings only."""

    flight = session.get(Flight, flight_id)
    if flight is None:
        raise FlightNotFoundError(f"No flight exists with id {flight_id}.")

    labels = canonical_seat_labels(flight.total_seats)
    occupied = session.scalars(
        select(Booking.seat_number).where(
            Booking.flight_id == flight_id,
            Booking.booking_status == BookingStatus.CONFIRMED,
        ),
    ).all()

    normalized_taken = {normalize_seat_code(str(s)) for s in occupied}

    grouped: dict[int, list[SeatMapTile]] = defaultdict(list)
    for label in labels:
        rn = row_number_from_label(label)
        grouped[rn].append(
            SeatMapTile(
                seat_number=label,
                available=(normalize_seat_code(label) not in normalized_taken),
            ),
        )

    ordered_rows = [grouped[row_n] for row_n in sorted(grouped)]

    return SeatMapOut(
        flight_id=flight.id,
        total_seats=flight.total_seats,
        columns_per_full_row=CANON_COLUMNS_PER_ROW,
        rows=ordered_rows,
    )
