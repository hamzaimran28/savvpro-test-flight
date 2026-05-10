"""Domain errors raised by services. HTTP status codes are assigned in ``app.api.exception_handlers``."""

from __future__ import annotations


class AppError(Exception):
    """Base for intentional business/domain failures (not programmer bugs)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FlightNotFoundError(AppError):
    """No flight matches the supplied identifier."""

    pass


class NoSeatsAvailableError(AppError):
    """Flight is full or the last seat was taken by another request."""

    pass


class SeatAlreadyHeldError(AppError):
    """An active (CONFIRMED) booking already uses this seat on this flight."""

    pass


class InvalidSeatError(AppError):
    """Chosen seat label is unknown for this aircraft configuration."""

    pass


class BookingNotFoundError(AppError):
    """No booking matches the supplied reference."""

    pass


class BookingAlreadyCancelledError(AppError):
    """Cancellation was requested for a booking that is not active."""

    pass


class InventoryInvariantError(AppError):
    """Seat counters and booking rows are inconsistent — operator or data repair may be needed."""

    pass
