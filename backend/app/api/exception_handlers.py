"""Map domain exceptions to HTTP responses — keeps routers free of copy-pasted try/except."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.exceptions import (
    AppError,
    BookingAlreadyCancelledError,
    BookingNotFoundError,
    FlightNotFoundError,
    InventoryInvariantError,
    NoSeatsAvailableError,
    SeatAlreadyHeldError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers for FlightHub domain errors (explicit types for predictable Starlette routing)."""

    mapping: dict[type[AppError], int] = {
        FlightNotFoundError: 404,
        BookingNotFoundError: 404,
        NoSeatsAvailableError: 409,
        SeatAlreadyHeldError: 409,
        BookingAlreadyCancelledError: 409,
        InventoryInvariantError: 500,
    }

    def make_handler(status_code: int):
        async def _handler(_request: Request, exc: AppError) -> JSONResponse:
            return JSONResponse(
                status_code=status_code,
                content={"detail": exc.detail},
            )

        return _handler

    for exc_type, status_code in mapping.items():
        app.add_exception_handler(exc_type, make_handler(status_code))
