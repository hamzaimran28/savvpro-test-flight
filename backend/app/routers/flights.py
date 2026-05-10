"""Flight HTTP surface — maps requests to ``flight_service`` and response models."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep
from app.schemas.flight import FlightOut, FlightSearchQuery, SeatMapOut
from app.services import flight_service

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("", response_model=list[FlightOut])
def list_flights(session: SessionDep) -> list[FlightOut]:
    """Return the full schedule including sold-out flights."""
    return [
        flight_service.flight_as_out(session, row)
        for row in flight_service.list_flights(session)
    ]


@router.get("/search", response_model=list[FlightOut])
def search_flights(
    session: SessionDep,
    filters: Annotated[FlightSearchQuery, Depends()],
) -> list[FlightOut]:
    """Return flights with available inventory that match optional search filters."""
    rows = flight_service.search_flights(session, filters)
    return [flight_service.flight_as_out(session, row) for row in rows]


@router.get("/{flight_id}/seat-map", response_model=SeatMapOut)
def seat_map(session: SessionDep, flight_id: int) -> SeatMapOut:
    """Return deterministic cabin seating grid and which positions are currently free."""

    return flight_service.seat_map_for_flight(session, flight_id)
