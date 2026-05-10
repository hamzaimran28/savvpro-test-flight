"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.booking import BookingLookupQuery


def _booking_lookup_query(
    booking_reference: Annotated[
        str | None,
        Query(max_length=32, description="Exact booking reference"),
    ] = None,
    passenger_full_name: Annotated[
        str | None,
        Query(max_length=500, description="Exact name match (case-insensitive lookup)"),
    ] = None,
) -> BookingLookupQuery:
    """
    Build ``BookingLookupQuery`` from plain query strings.

    Converts Pydantic ``ValidationError`` into **422** so lookup mistakes never surface as 500s.
    """
    try:
        return BookingLookupQuery(
            booking_reference=booking_reference,
            passenger_full_name=passenger_full_name,
        )
    except ValidationError as exc:
        # Omit non-JSON-safe objects (e.g. ``ctx`` may embed ``ValueError`` instances).
        safe_errors: list[dict[str, object]] = [
            {
                "type": err.get("type"),
                "loc": err.get("loc"),
                "msg": err.get("msg"),
                "input": err.get("input"),
            }
            for err in exc.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=safe_errors,
        ) from exc


BookingLookupDep = Annotated[BookingLookupQuery, Depends(_booking_lookup_query)]

SessionDep = Annotated[Session, Depends(get_db)]
