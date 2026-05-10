"""Flight ORM model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.booking import Booking


class Flight(Base):
    """Scheduled flight with fixed capacity and per-seat pricing."""

    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    destination: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    departure_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_seat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_available: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    bookings: Mapped[list[Booking]] = relationship(
        "Booking",
        back_populates="flight",
        cascade="all, delete-orphan",
    )
