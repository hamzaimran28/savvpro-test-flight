"""Booking lifecycle: atomic inventory mutation, lookups, cancellations."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.exceptions import (
    BookingAlreadyCancelledError,
    BookingNotFoundError,
    FlightNotFoundError,
    InventoryInvariantError,
    NoSeatsAvailableError,
    SeatAlreadyHeldError,
)
from app.models.booking import Booking, BookingStatus
from app.models.flight import Flight
from app.schemas.booking import BookingLookupQuery


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
    - Run a guarded ``UPDATE`` that decrements ``seats_available`` only while stock remains.
    - Insert the ``CONFIRMED`` booking; the partial unique index rejects duplicate active seats.

    If anything fails after the ``UPDATE``, the session is rolled back so inventory counters stay
    aligned with confirmed rows.

    We use explicit ``commit()`` / ``rollback()`` (not nested ``session.begin()`` blocks) so this
    path stays predictable with SQLite’s default implicit transaction/autobegin behaviour.
    """
    normalized_name = passenger_full_name.strip()
    normalized_passport = passport_number.strip()
    normalized_seat = seat_number.strip().upper()

    if session.get(Flight, flight_id) is None:
        raise FlightNotFoundError(f"No flight exists with id {flight_id}.")

    booking_row: Booking

    try:
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
            "That seat already has an active booking on this flight. Pick a different seat.",
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


def cancel_booking(session: Session, *, booking_reference: str) -> Booking:
    """Increase ``seats_available`` (guarded) and mark the reservation ``CANCELLED``."""
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
        restore = session.execute(
            update(Flight)
            .where(
                Flight.id == booking_row.flight_id,
                Flight.seats_available < Flight.total_seats,
            )
            .values(seats_available=Flight.seats_available + 1),
        )
        if restore.rowcount != 1:
            session.rollback()
            raise InventoryInvariantError(
                "Seat inventory could not be restored (internal consistency check failed). "
                "The booking was left unchanged.",
            )

        booking_row.booking_status = BookingStatus.CANCELLED
        booking_row.cancelled_at = _utcnow()
        session.flush()
    except InventoryInvariantError:
        raise
    except Exception:
        session.rollback()
        raise

    session.commit()
    session.refresh(booking_row)
    return booking_row
