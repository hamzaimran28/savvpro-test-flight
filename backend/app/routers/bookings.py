"""Booking HTTP surface — validation via Pydantic; domain rules live in ``booking_service``."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import BookingLookupDep, SessionDep
from app.schemas.booking import BookingCreate, BookingOut
from app.services import booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_booking(
    payload: BookingCreate,
    session: SessionDep,
) -> BookingOut:
    """Create a confirmed reservation; ``booking_reference`` is generated server-side."""
    row = booking_service.create_booking(
        session,
        flight_id=payload.flight_id,
        passenger_full_name=payload.passenger_full_name,
        passport_number=payload.passport_number,
        seat_number=payload.seat_number,
    )
    return booking_service.booking_as_out(session, row)


@router.get("", response_model=list[BookingOut])
def list_bookings(
    session: SessionDep,
    lookup: BookingLookupDep,
) -> list[BookingOut]:
    """Find bookings by immutable reference or passenger name (mutually exclusive filters)."""
    rows = booking_service.lookup_bookings(session, filters=lookup)
    return [booking_service.booking_as_out(session, r) for r in rows]


@router.delete("/{booking_reference}", response_model=BookingOut)
def cancel_booking_via_delete(
    booking_reference: str,
    session: SessionDep,
) -> BookingOut:
    """Cancel by ``booking_reference`` (REST DELETE)."""
    row = booking_service.cancel_booking(session, booking_reference=booking_reference)
    return booking_service.booking_as_out(session, row)


@router.post("/{booking_reference}/cancel", response_model=BookingOut)
def cancel_booking_via_post(
    booking_reference: str,
    session: SessionDep,
) -> BookingOut:
    """Alternative cancel for clients that cannot issue DELETE requests."""
    row = booking_service.cancel_booking(session, booking_reference=booking_reference)
    return booking_service.booking_as_out(session, row)
