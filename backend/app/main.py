"""FlightHub FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.db.session import init_db
from app.routers.bookings import router as bookings_router
from app.routers.flights import router as flights_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="FlightHub",
        description="Internal flight search and booking API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(flights_router)
    application.include_router(bookings_router)
    return application


app = create_app()
