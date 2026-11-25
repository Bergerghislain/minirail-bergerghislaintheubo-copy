"""Idempotency-key primitives for booking creation. Flushes, never commits."""

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import IdempotencyKey
from minirail.utils.exc import IdempotencyConflictException


def find_idempotency(session: MinirailSession, *, sales_channel_id: int, key: str) -> IdempotencyKey | None:
    return session.scalars(
        select(IdempotencyKey).where(
            IdempotencyKey.sales_channel_id == sales_channel_id,
            IdempotencyKey.key == key,
        )
    ).one_or_none()


def store_idempotency(
    session: MinirailSession,
    *,
    sales_channel_id: int,
    key: str,
    request_hash: str,
    booking_key: str,
) -> IdempotencyKey:
    existing = find_idempotency(session, sales_channel_id=sales_channel_id, key=key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictException("Idempotency-Key was reused with a different request body")
        return existing
    record = IdempotencyKey(
        sales_channel_id=sales_channel_id,
        key=key,
        request_hash=request_hash,
        booking_key=booking_key,
    )
    session.add(record)
    session.flush()
    return record
