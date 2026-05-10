"""Flight listing and search (read-side query logic only)."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.flight import Flight
from app.schemas.flight import FlightSearchQuery


def list_flights(session: Session) -> list[Flight]:
    """Return every flight, soonest departure first."""
    stmt = select(Flight).order_by(Flight.departure_datetime.asc())
    return list(session.scalars(stmt).all())


def search_flights(session: Session, filters: FlightSearchQuery) -> list[Flight]:
    """
    Find flights matching optional criteria.

    Only rows with inventory (``seats_available > 0``) appear — this is the “bookable” search.
    Origin and destination comparisons are case-insensitive when provided.
    Departure filters use the UTC calendar day of ``flight.departure_datetime``.
    """
    stmt = select(Flight).where(Flight.seats_available > 0)

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
    return list(session.scalars(stmt).all())
