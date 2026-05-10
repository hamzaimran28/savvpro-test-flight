"""Pydantic models for bookings (responses, bodies, and validated lookups)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.booking import BookingStatus
from app.schemas.flight import FlightOut


class BookingCreate(BaseModel):
    """Request body for creating a confirmed reservation."""

    passenger_full_name: str = Field(min_length=1, max_length=500)
    passport_number: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9]+$",
        description="Machine-readable passport or ID reference (letters and digits only).",
    )
    flight_id: int = Field(gt=0)
    seat_number: str = Field(min_length=1, max_length=16)

    model_config = ConfigDict(str_strip_whitespace=True)


class BookingLookupQuery(BaseModel):
    """Query parameters for passenger or reference lookup."""

    booking_reference: str | None = Field(default=None, max_length=32)
    passenger_full_name: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def exactly_one_filter(self) -> "BookingLookupQuery":
        ref = None if self.booking_reference is None else self.booking_reference.strip() or None
        name = None if self.passenger_full_name is None else self.passenger_full_name.strip() or None
        self.booking_reference = ref
        self.passenger_full_name = name
        if ref and name:
            raise ValueError(
                "Provide only one filter: booking_reference or passenger_full_name (not both).",
            )
        if not ref and not name:
            raise ValueError(
                "Provide booking_reference or passenger_full_name as a query parameter.",
            )
        return self


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
