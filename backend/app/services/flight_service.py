"""Flight listing and search (query) logic."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.flight import Flight


def list_flights(db: Session) -> list[Flight]:
    """Return every flight row, ordered by departure time (soonest first)."""
    stmt = select(Flight).order_by(Flight.departure_datetime.asc())
    return list(db.scalars(stmt).all())


def search_flights(
    db: Session,
    *,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[date] = None,
) -> list[Flight]:
    """
    Return flights matching optional filters.

    Only rows with ``seats_available > 0`` are included (bookable inventory).
    Origin and destination are matched case-insensitively when provided.
    Departure date compares the calendar day in UTC against ``departure_datetime``.
    """
    stmt = select(Flight).where(Flight.seats_available > 0)

    if origin is not None and origin.strip():
        needle = origin.strip().lower()
        stmt = stmt.where(func.lower(Flight.origin) == needle)

    if destination is not None and destination.strip():
        needle = destination.strip().lower()
        stmt = stmt.where(func.lower(Flight.destination) == needle)

    if departure_date is not None:
        start = datetime.combine(departure_date, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        stmt = stmt.where(
            Flight.departure_datetime >= start,
            Flight.departure_datetime < end,
        )

    stmt = stmt.order_by(Flight.departure_datetime.asc())
    return list(db.scalars(stmt).all())
