"""Canonical seat numbering for FlightHub demos (fixed seats-per-row cabin)."""

from __future__ import annotations

import re
from functools import lru_cache

CANON_COLUMNS_PER_ROW = 6

SEAT_PATTERN = re.compile(r"^(\d+)([A-Z])$")


def normalize_seat_code(raw: str) -> str:
    """Upper-case, trimmed, whitespace removed (e.g. ``' 12 c ' → '12C'``)."""

    return raw.strip().upper().replace(" ", "")


@lru_cache(maxsize=256)
def _labels_tuple(total_seats: int, columns_per_row: int) -> tuple[str, ...]:
    if total_seats < 1:
        msg = "total_seats must be at least 1"
        raise ValueError(msg)
    if columns_per_row < 1:
        msg = "columns_per_row must be at least 1"
        raise ValueError(msg)

    labels: list[str] = []
    for i in range(total_seats):
        row = i // columns_per_row + 1
        letter_index = i % columns_per_row
        letter = chr(65 + letter_index)
        labels.append(f"{row}{letter}")
    return tuple(labels)


def canonical_seat_labels(total_seats: int, *, columns_per_row: int = CANON_COLUMNS_PER_ROW) -> tuple[str, ...]:
    """
    Produce exactly ``total_seats`` identifiers in row-major ``{row}{A..}`` order.

    Example (6 columns): positions 7–12 are ``2A`` … ``2F``; layouts with remainder omit trailing
    seats in the last row only (never ghost seats beyond ``total_seats``).
    """

    return _labels_tuple(total_seats, columns_per_row)


def is_valid_seat_for_aircraft(total_seats: int, seat: str, *, columns_per_row: int = CANON_COLUMNS_PER_ROW) -> bool:
    """Return True if ``seat`` maps to exactly one canonical label on this aircraft."""

    return normalize_seat_code(seat) in frozenset(
        canonical_seat_labels(total_seats, columns_per_row=columns_per_row),
    )


def row_number_from_label(label: str) -> int:
    normalized = normalize_seat_code(label)
    parsed = SEAT_PATTERN.fullmatch(normalized)
    if not parsed:
        msg = f"Malformed seat label: {label!r}"
        raise ValueError(msg)
    return int(parsed.group(1))
