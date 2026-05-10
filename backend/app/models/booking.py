"""Booking ORM model."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.flight import Flight


class BookingStatus(str, enum.Enum):
    """Lifecycle state of a booking."""

    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Booking(Base):
    """Passenger reservation against a single flight."""

    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "uq_booking_flight_seat_confirmed",
            "flight_id",
            "seat_number",
            unique=True,
            sqlite_where=text("booking_status = 'CONFIRMED'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_reference: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )
    flight_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("flights.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    passenger_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    passport_number: Mapped[str] = mapped_column(String(32), nullable=False)
    seat_number: Mapped[str] = mapped_column(String(16), nullable=False)

    booking_status: Mapped[BookingStatus] = mapped_column(
        SqlEnum(
            BookingStatus,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=BookingStatus.CONFIRMED,
        server_default=BookingStatus.CONFIRMED.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    flight: Mapped[Flight] = relationship("Flight", back_populates="bookings")
