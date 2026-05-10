"""HTTP routes for bookings (thin — delegates to booking service)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.exceptions import (
    BookingAlreadyCancelledError,
    BookingLookupValidationError,
    BookingNotFoundError,
    FlightNotFoundError,
    InventoryInvariantError,
    NoSeatsAvailableError,
    SeatAlreadyHeldError,
)
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingOut
from app.services import booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _cancel_booking_http(db: Session, booking_reference: str) -> Booking:
    try:
        return booking_service.cancel_booking(db, booking_reference=booking_reference)
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
    except BookingAlreadyCancelledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
    except InventoryInvariantError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.detail,
        ) from exc


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def post_booking(payload: BookingCreate, db: Session = Depends(get_db)) -> Booking:
    try:
        return booking_service.create_booking(
            db,
            flight_id=payload.flight_id,
            passenger_full_name=payload.passenger_full_name,
            passport_number=payload.passport_number,
            seat_number=payload.seat_number,
        )
    except FlightNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
    except NoSeatsAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
    except SeatAlreadyHeldError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
    except InventoryInvariantError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.detail,
        ) from exc


@router.get("", response_model=list[BookingOut])
def get_bookings(
    db: Session = Depends(get_db),
    booking_reference: Annotated[
        str | None,
        Query(max_length=32, description="Exact booking reference"),
    ] = None,
    passenger_full_name: Annotated[
        str | None,
        Query(max_length=500, description="Exact passenger match (case-insensitive)"),
    ] = None,
) -> list[Booking]:
    try:
        return booking_service.lookup_bookings(
            db,
            booking_reference=booking_reference,
            passenger_full_name=passenger_full_name,
        )
    except BookingLookupValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.detail,
        ) from exc


@router.delete(
    "/{booking_reference}",
    response_model=BookingOut,
)
def delete_booking(
    booking_reference: str,
    db: Session = Depends(get_db),
) -> Booking:
    return _cancel_booking_http(db, booking_reference)


@router.post(
    "/{booking_reference}/cancel",
    response_model=BookingOut,
)
def post_cancel_booking(
    booking_reference: str,
    db: Session = Depends(get_db),
) -> Booking:
    """Cancel using POST for clients that prefer a non-idempotent-safe verb semantics."""

    return _cancel_booking_http(db, booking_reference)
