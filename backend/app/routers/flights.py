"""HTTP routes for flights (thin — delegates to services)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.flight import Flight
from app.schemas.flight import FlightOut
from app.services import flight_service

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("", response_model=list[FlightOut])
def get_flights(db: Session = Depends(get_db)) -> list[Flight]:
    """List all scheduled flights (includes sold-out flights)."""
    return flight_service.list_flights(db)


@router.get("/search", response_model=list[FlightOut])
def search_flights(
    db: Session = Depends(get_db),
    origin: Annotated[
        str | None,
        Query(max_length=64, description="Filter by origin (case-insensitive)"),
    ] = None,
    destination: Annotated[
        str | None,
        Query(max_length=64, description="Filter by destination (case-insensitive)"),
    ] = None,
    departure_date: Annotated[
        date | None,
        Query(description="Filter by departure calendar day (UTC)"),
    ] = None,
) -> list[Flight]:
    """
    Search bookable flights.

    All query parameters are optional. Results include only flights with at least one
    available seat (`seats_available > 0`).
    """
    return flight_service.search_flights(
        db,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
    )
