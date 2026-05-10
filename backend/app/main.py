"""FlightHub FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.db.session import SessionLocal, init_db
from app.routers.bookings import router as bookings_router
from app.routers.flights import router as flights_router
from app.services import flight_service

_RESET_SQLITE_ENV = frozenset({"1", "true", "yes", "on"})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if (
        os.getenv("FLITHUB_RESET_SQLITE_ON_START", "").strip().lower()
        in _RESET_SQLITE_ENV
    ):
        with SessionLocal() as db:
            flight_service.purge_all_bookings_and_flights(db)
        print(
            "FlightHub: FLITHUB_RESET_SQLITE_ON_START cleared all flights and bookings.",
            flush=True,
        )
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="FlightHub",
        description="Internal flight search and booking API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(flights_router)
    application.include_router(bookings_router)
    return application


app = create_app()
