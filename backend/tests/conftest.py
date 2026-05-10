"""
Isolated SQLite per test + FastAPI TestClient.

``app.db.session`` binds ``engine`` / ``SessionLocal`` at import time, so each test
sets ``DATABASE_URL`` to a fresh file and reloads the application stack in a fixed
order so routes keep the correct ``Depends(get_db)`` binding.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_RELOAD_ORDER = (
    "app.db.session",
    "app.api.deps",
    "app.routers.flights",
    "app.routers.bookings",
    "app.main",
)


def _sqlite_url(db_path: Path) -> str:
    return "sqlite:///" + db_path.as_posix()


def _reload_application_stack() -> object:
    """Return a fresh FastAPI ``app`` bound to the current ``DATABASE_URL``."""
    for name in _RELOAD_ORDER:
        mod = sys.modules.get(name)
        if mod is not None:
            if name == "app.db.session" and getattr(mod, "engine", None) is not None:
                mod.engine.dispose()
            importlib.reload(mod)
        else:
            importlib.import_module(name)
    from app.main import app as application

    return application


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Empty schema; each test seeds its own rows via ``SessionLocal``."""
    db_file = tmp_path / "isolated.db"
    url = _sqlite_url(db_file)
    monkeypatch.setenv("DATABASE_URL", url)
    application = _reload_application_stack()
    try:
        with TestClient(application) as tc:
            yield tc
    finally:
        import app.db.session as session_mod

        if getattr(session_mod, "engine", None) is not None:
            session_mod.engine.dispose()


@pytest.fixture
def backend_root() -> Path:
    """``backend/`` directory (parent of ``tests/``)."""
    return Path(__file__).resolve().parent.parent
