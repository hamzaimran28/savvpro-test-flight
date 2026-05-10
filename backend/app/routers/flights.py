"""Flight HTTP surface — maps requests to ``flight_service`` and response models."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep
from app.models.flight import Flight
from app.schemas.flight import FlightOut, FlightSearchQuery
from app.services import flight_service

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("", response_model=list[FlightOut])
def list_flights(session: SessionDep) -> list[Flight]:
    """Return the full schedule including sold-out flights."""
    return flight_service.list_flights(session)


@router.get("/search", response_model=list[FlightOut])
def search_flights(
    session: SessionDep,
    filters: Annotated[FlightSearchQuery, Depends()],
) -> list[Flight]:
    """Return flights with available inventory that match optional search filters."""
    return flight_service.search_flights(session, filters)
