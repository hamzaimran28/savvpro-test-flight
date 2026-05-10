"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import init_db
from app.routers.bookings import router as bookings_router
from app.routers.flights import router as flights_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize database schema on startup."""
    init_db()
    yield


app = FastAPI(
    title="FlightHub",
    description="Internal flight search and booking API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(flights_router)
app.include_router(bookings_router)
