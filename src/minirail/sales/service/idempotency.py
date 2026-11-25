"""Idempotency-Key helpers for booking creation.

Everything here flushes and never commits — the caller owns the transaction.
"""

import hashlib
import json

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import BookingIdempotencyKey
from minirail.sales.schemas.booking import BookingCreateSchema
from minirail.utils.exc import IdempotencyKeyConflictException


def fingerprint_booking_create(payload: BookingCreateSchema) -> str:
    """Stable SHA-256 of the create body (snake_case JSON, sorted keys)."""
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_booking_idempotency(
    session: MinirailSession, *, sales_channel_id: int, key: str
) -> BookingIdempotencyKey | None:
    statement = select(BookingIdempotencyKey).where(
        BookingIdempotencyKey.sales_channel_id == sales_channel_id,
        BookingIdempotencyKey.key == key,
    )
    return session.scalars(statement).one_or_none()


def resolve_booking_idempotency(
    session: MinirailSession,
    *,
    sales_channel_id: int,
    key: str,
    request_hash: str,
) -> BookingIdempotencyKey | None:
    """Return the stored record on replay, or None if the key is free.

    Raises IdempotencyKeyConflictException when the key was used with another body.
    """
    existing = get_booking_idempotency(session, sales_channel_id=sales_channel_id, key=key)
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise IdempotencyKeyConflictException(f"Idempotency-Key {key!r} was already used with a different request body")
    return existing


def store_booking_idempotency(
    session: MinirailSession,
    *,
    sales_channel_id: int,
    key: str,
    request_hash: str,
    booking_id: int,
) -> BookingIdempotencyKey:
    record = BookingIdempotencyKey(
        sales_channel_id=sales_channel_id,
        key=key,
        request_hash=request_hash,
        booking_id=booking_id,
    )
    session.add(record)
    session.flush()
    return record
