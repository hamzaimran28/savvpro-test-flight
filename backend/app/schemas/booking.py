"""Pydantic models for booking API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus
from app.schemas.flight import FlightOut


class BookingCreate(BaseModel):
    passenger_full_name: str = Field(min_length=1, max_length=500)
    passport_number: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    flight_id: int = Field(gt=0)
    seat_number: str = Field(min_length=1, max_length=16)

    model_config = ConfigDict(str_strip_whitespace=True)


class BookingOut(BaseModel):
    booking_reference: str
    passenger_full_name: str
    passport_number: str
    seat_number: str
    booking_status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
    flight: FlightOut

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
