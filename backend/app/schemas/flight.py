"""Pydantic models for flight API responses and query parameters."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class FlightOut(BaseModel):
    """Flight returned to clients (read model)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    origin: str
    destination: str
    departure_datetime: datetime
    duration_minutes: int = Field(ge=0)
    price_per_seat: Decimal
    total_seats: int = Field(ge=0)
    seats_available: int = Field(ge=0)
    created_at: datetime
