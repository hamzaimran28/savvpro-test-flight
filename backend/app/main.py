"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import init_db


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
