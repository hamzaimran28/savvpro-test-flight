"""Pydantic models for flights (responses and validated query/input)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class FlightSearchQuery(BaseModel):
    """Optional query filters for finding bookable flights (``GET /flights/search``)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    origin: str | None = Field(default=None, max_length=64)
    destination: str | None = Field(default=None, max_length=64)
    departure_date: date | None = None

    @model_validator(mode="after")
    def empty_strings_to_none(self) -> "FlightSearchQuery":
        if self.origin == "":
            self.origin = None
        if self.destination == "":
            self.destination = None
        return self
