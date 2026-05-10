"""Domain-level errors mapped to HTTP in exception handlers."""

from __future__ import annotations


class AppError(Exception):
    """Base for application-level errors."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FlightNotFoundError(AppError):
    pass


class NoSeatsAvailableError(AppError):
    pass


class SeatAlreadyHeldError(AppError):
    """Active booking already occupies this seat on the flight."""

    pass


class BookingNotFoundError(AppError):
    pass


class BookingAlreadyCancelledError(AppError):
    pass


class InventoryInvariantError(AppError):
    """Inventory could not be updated consistently (unexpected state)."""

    pass


class BookingLookupValidationError(AppError):
    """Invalid parameters for lookup (e.g. missing filters)."""

    pass
