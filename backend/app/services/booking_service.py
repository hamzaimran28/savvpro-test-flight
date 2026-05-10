"""Booking creation, lookup, cancellation — transactional inventory rules."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.exceptions import (
    BookingAlreadyCancelledError,
    BookingLookupValidationError,
    BookingNotFoundError,
    FlightNotFoundError,
    InventoryInvariantError,
    NoSeatsAvailableError,
    SeatAlreadyHeldError,
)
from app.models.booking import Booking, BookingStatus
from app.models.flight import Flight


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_booking_reference(db: Session) -> str:
    for _ in range(16):
        ref = secrets.token_urlsafe(12)[:31]
        if db.scalar(select(Booking.id).where(Booking.booking_reference == ref).limit(1)):
            continue
        return ref
    msg = "Could not allocate a unique booking reference"
    raise InventoryInvariantError(msg)


def create_booking(
    db: Session,
    *,
    flight_id: int,
    passenger_full_name: str,
    passport_number: str,
    seat_number: str,
) -> Booking:
    """
    Create a confirmed booking inside a single transaction:

    1. Ensure flight exists.
    2. Atomically decrement ``seats_available`` only while stock remains.
    3. Insert booking (server-generated reference; partial unique index enforces seat).

    On any failure after a write, the session is rolled back so inventory stays consistent.
    """
    name = passenger_full_name.strip()
    passport = passport_number.strip()
    seat = seat_number.strip().upper()

    flight = db.get(Flight, flight_id)
    if flight is None:
        raise FlightNotFoundError(f"Flight with id {flight_id} does not exist")

    try:
        dec = (
            update(Flight)
            .where(
                Flight.id == flight_id,
                Flight.seats_available > 0,
            )
            .values(seats_available=Flight.seats_available - 1)
        )
        result = db.execute(dec)
        if result.rowcount != 1:
            raise NoSeatsAvailableError(
                "No seats available for this flight; booking could not be completed.",
            )

        reference = _generate_booking_reference(db)
        booking = Booking(
            booking_reference=reference,
            flight_id=flight_id,
            passenger_full_name=name,
            passport_number=passport,
            seat_number=seat,
            booking_status=BookingStatus.CONFIRMED,
            cancelled_at=None,
        )
        db.add(booking)
        db.flush()
    except NoSeatsAvailableError:
        db.rollback()
        raise
    except InventoryInvariantError:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise SeatAlreadyHeldError(
            "This seat is already booked on this flight, or the booking reference collided.",
        ) from None
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(booking)
    return booking


def lookup_bookings(
    db: Session,
    *,
    booking_reference: str | None,
    passenger_full_name: str | None,
) -> list[Booking]:
    stmt = select(Booking).options(selectinload(Booking.flight))

    ref = booking_reference.strip() if booking_reference else None
    name = passenger_full_name.strip() if passenger_full_name else None

    if ref and name:
        raise BookingLookupValidationError(
            "Provide only one of booking_reference or passenger_full_name, not both.",
        )

    if ref:
        stmt = stmt.where(Booking.booking_reference == ref)
    elif name:
        stmt = stmt.where(func.lower(Booking.passenger_full_name) == name.lower())
    else:
        raise BookingLookupValidationError(
            "Provide either booking_reference or passenger_full_name as a query parameter.",
        )

    stmt = stmt.order_by(Booking.created_at.desc())
    return list(db.scalars(stmt).all())


def cancel_booking(db: Session, *, booking_reference: str) -> Booking:
    """Cancel by reference: restore inventory and mark CANCELLED in one transaction."""
    ref = booking_reference.strip()
    if not ref:
        raise BookingNotFoundError("Booking reference is required")

    booking = db.scalar(select(Booking).where(Booking.booking_reference == ref))
    if booking is None:
        raise BookingNotFoundError(f"Booking '{ref}' does not exist")

    if booking.booking_status == BookingStatus.CANCELLED:
        raise BookingAlreadyCancelledError(f"Booking '{ref}' is already cancelled.")

    try:
        inc = (
            update(Flight)
            .where(
                Flight.id == booking.flight_id,
                Flight.seats_available < Flight.total_seats,
            )
            .values(seats_available=Flight.seats_available + 1)
        )
        res = db.execute(inc)
        if res.rowcount != 1:
            raise InventoryInvariantError(
                "Could not restore seat inventory; flight seat counts may be inconsistent.",
            )

        booking.booking_status = BookingStatus.CANCELLED
        booking.cancelled_at = _utcnow()
        db.flush()
    except InventoryInvariantError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(booking)
    return booking
