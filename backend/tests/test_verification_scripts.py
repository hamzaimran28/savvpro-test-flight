"""Run ``scripts/*.py`` verifications as subprocess suites (standalone temp DB each)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.parametrize(
    "script_name",
    [
        "verify_booking_api.py",
        "verify_flight_api.py",
        "verify_overbooking_concurrency.py",
    ],
)
def test_script_exits_successfully(backend_root: Path, script_name: str) -> None:
    """Each script configures its own ``DATABASE_URL`` and must finish with status 0."""
    script_path = backend_root / "scripts" / script_name
    assert script_path.is_file(), f"Missing {script_path}"
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(backend_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"{script_name} failed ({proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
