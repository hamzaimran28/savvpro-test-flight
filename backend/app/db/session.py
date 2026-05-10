"""SQLite engine, session factory, and schema initialization."""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base

# Default: single SQLite file next to CWD when running uvicorn from `backend/`
_DEFAULT_SQLITE_URL = "sqlite:///./flighthub.db"

DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_SQLITE_URL)


def _create_engine() -> Engine:
    connect_args: dict = {}
    if DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Retry briefly on SQLITE_BUSY when concurrent writers contend on the same DB file.
        connect_args["timeout"] = 30.0
    return create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


engine = _create_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    """Create all tables registered on ``Base.metadata``."""
    # Import models so they register with metadata before create_all
    import app.models.booking  # noqa: F401
    import app.models.flight  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
