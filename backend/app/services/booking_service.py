"""Booking lifecycle: atomic inventory mutation, lookups, cancellations."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.domain.cabin_layout import (
    canonical_seat_labels,
    is_valid_seat_for_aircraft,
    normalize_seat_code,
)
from app.exceptions import (
    BookingAlreadyCancelledError,
    BookingNotFoundError,
    FlightNotFoundError,
    InventoryInvariantError,
    InvalidSeatError,
    NoSeatsAvailableError,
    SeatAlreadyHeldError,
)
from app.models.booking import Booking, BookingStatus
from app.models.flight import Flight
from app.schemas.booking import BookingLookupQuery, BookingOut
from app.services import flight_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _allocate_booking_reference(session: Session) -> str:
    """Generate a collision-resistant booking reference checked against the DB."""
    for _ in range(16):
        candidate = secrets.token_urlsafe(12)[:31]
        exists = session.scalar(
            select(Booking.id).where(Booking.booking_reference == candidate).limit(1),
        )
        if exists is None:
            return candidate
    raise InventoryInvariantError(
        "Unable to allocate a unique booking_reference after repeated attempts.",
    )


def create_booking(
    session: Session,
    *,
    flight_id: int,
    passenger_full_name: str,
    passport_number: str,
    seat_number: str,
) -> Booking:
    """
    Reserve one confirmed seat atomically:

    - Ensure the flight exists.
    - Require a **canonical cabin code** (`{row}` + `{A-F}` slices for this airline’s simplified layout).
    - Reject duplicates before inventory work when possible (still rely on uniqueness + IntegrityError races).
    - Run a guarded ``UPDATE`` then insert the booking.

    Seat layout rules mirror ``GET /flights/{flight_id}/seat-map``.
    """

    normalized_name = passenger_full_name.strip()
    normalized_passport = passport_number.strip()
    normalized_seat = normalize_seat_code(seat_number)

    flight_row = session.get(Flight, flight_id)
    if flight_row is None:
        raise FlightNotFoundError(f"No flight exists with id {flight_id}.")

    if not is_valid_seat_for_aircraft(flight_row.total_seats, normalized_seat):
        catalogue = canonical_seat_labels(flight_row.total_seats)
        peek_list = catalogue[:10]
        tail = "" if len(catalogue) <= 10 else " …"
        sample = ", ".join(peek_list) + tail
        raise InvalidSeatError(
            f"'{normalized_seat}' is not a valid cabin position on this aircraft. "
            f"Open the seating chart via GET /flights/{{id}}/seat-map or choose one of "
            f"{len(catalogue)} installed seats (e.g. {sample}).",
        )

    taken = session.scalar(
        select(Booking.id).where(
            Booking.flight_id == flight_id,
            Booking.booking_status == BookingStatus.CONFIRMED,
            Booking.seat_number == normalized_seat,
        ).limit(1),
    )
    if taken is not None:
        raise SeatAlreadyHeldError(
            f"Seat {normalized_seat} already has an active booking on flight {flight_id}.",
        )

    booking_row: Booking

    try:
        flight_service.reconcile_flight_inventory(session, flight_row)
        session.flush()
        if flight_row.seats_available <= 0:
            raise NoSeatsAvailableError(
                "This flight has no seats left. Another traveller may have taken the last seat.",
            )

        claim = session.execute(
            update(Flight)
            .where(
                Flight.id == flight_id,
                Flight.seats_available > 0,
            )
            .values(seats_available=Flight.seats_available - 1),
        )
        if claim.rowcount != 1:
            raise NoSeatsAvailableError(
                "This flight has no seats left. Another traveller may have taken the last seat.",
            )

        reference = _allocate_booking_reference(session)
        booking_row = Booking(
            booking_reference=reference,
            flight_id=flight_id,
            passenger_full_name=normalized_name,
            passport_number=normalized_passport,
            seat_number=normalized_seat,
            booking_status=BookingStatus.CONFIRMED,
            cancelled_at=None,
        )
        session.add(booking_row)
        session.flush()
    except NoSeatsAvailableError:
        session.rollback()
        raise
    except InventoryInvariantError:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise SeatAlreadyHeldError(
            "That seat was reserved by someone else simultaneously. Refresh the seating chart.",
        ) from exc
    except Exception:
        session.rollback()
        raise

    session.commit()
    session.refresh(booking_row)
    return booking_row


def lookup_bookings(session: Session, *, filters: BookingLookupQuery) -> list[Booking]:
    """
    Lookup by reference (exact) or passenger legal name (case-insensitive equality).

    ``BookingLookupQuery`` guarantees exactly one discriminator is populated at the router layer.
    """
    stmt = select(Booking).options(selectinload(Booking.flight))

    if filters.booking_reference is not None:
        stmt = stmt.where(Booking.booking_reference == filters.booking_reference)
    elif filters.passenger_full_name is not None:
        stmt = stmt.where(
            func.lower(Booking.passenger_full_name)
            == filters.passenger_full_name.lower(),
        )
    else:
        # BookingLookupQuery enforces exactly one discriminator; never return unfiltered rows.
        return []

    stmt = stmt.order_by(Booking.created_at.desc())
    return list(session.scalars(stmt).all())


def booking_as_out(session: Session, booking_row: Booking) -> BookingOut:
    """Serialize a booking with **derived** ``flight.seats_available`` (matches seat-map truth)."""

    flight_orm = booking_row.flight
    if flight_orm is None:
        flight_orm = session.get(Flight, booking_row.flight_id)
    if flight_orm is None:
        raise InventoryInvariantError(
            f"Flight id {booking_row.flight_id} missing while building booking response.",
        )

    return BookingOut(
        booking_reference=booking_row.booking_reference,
        passenger_full_name=booking_row.passenger_full_name,
        passport_number=booking_row.passport_number,
        seat_number=booking_row.seat_number,
        booking_status=booking_row.booking_status,
        created_at=booking_row.created_at,
        cancelled_at=booking_row.cancelled_at,
        flight=flight_service.flight_as_out(session, flight_orm),
    )


def cancel_booking(session: Session, *, booking_reference: str) -> Booking:
    """Mark the reservation ``CANCELLED`` and recompute flight inventory from bookings."""
    trimmed_ref = booking_reference.strip()
    if not trimmed_ref:
        raise BookingNotFoundError("Missing booking_reference; cannot cancel.")

    booking_row = session.scalar(
        select(Booking).where(Booking.booking_reference == trimmed_ref),
    )
    if booking_row is None:
        raise BookingNotFoundError(f"No booking exists with reference “{trimmed_ref}”.")
    if booking_row.booking_status == BookingStatus.CANCELLED:
        raise BookingAlreadyCancelledError(
            f"Booking “{trimmed_ref}” is already cancelled.",
        )

    try:
        booking_row.booking_status = BookingStatus.CANCELLED
        booking_row.cancelled_at = _utcnow()
        session.flush()

        flight_for_row = booking_row.flight
        if flight_for_row is None:
            flight_for_row = session.get(Flight, booking_row.flight_id)
        if flight_for_row is None:
            session.rollback()
            raise InventoryInvariantError(
                "Flight row missing while cancelling; booking was not committed.",
            )
        flight_service.reconcile_flight_inventory(session, flight_for_row)
    except InventoryInvariantError:
        raise
    except Exception:
        session.rollback()
        raise

    session.commit()
    session.refresh(booking_row)
    return booking_row
