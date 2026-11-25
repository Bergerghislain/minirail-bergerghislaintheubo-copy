"""Booking endpoints.

The endpoint owns the unit of work: it runs a job, commits once, and only
then triggers side effects (enqueue background messages, invalidate caches).
Side effects before the commit would reference state that might roll back.

Expiry scheduling uses a transactional outbox: the message row is inserted in
the same transaction as the booking, then published after commit. Payment runs
outside any open transaction (claim → charge → finalize/abort).
"""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.sales.actors.notifications import send_booking_notification
from minirail.sales.fetcher.booking import BookingFetcher
from minirail.sales.jobs.cancel_booking import CancelBookingJob
from minirail.sales.jobs.confirm_booking import (
    AbortConfirmBookingJob,
    ClaimConfirmBookingJob,
    FinalizeConfirmBookingJob,
)
from minirail.sales.jobs.create_booking import CreateBookingJob
from minirail.sales.schemas.booking import BookingConfirmSchema, BookingCreateSchema, BookingOutputSchema
from minirail.sales.service.idempotency import find_idempotency, store_idempotency
from minirail.sales.service.outbox import enqueue_outbox, publish_pending_outbox
from minirail.utils import payments
from minirail.utils.api import session_transaction
from minirail.utils.app import get_app, get_session
from minirail.utils.auth import CurrentSalesChannel
from minirail.utils.exc import PaymentDeclinedException

router = APIRouter(prefix="/api/bookings", tags=["sales"])


def _request_hash(payload: BookingCreateSchema) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@router.post("/", status_code=201)
def create_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    payload: BookingCreateSchema,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BookingOutputSchema:
    if idempotency_key is not None:
        existing = find_idempotency(session, sales_channel_id=sales_channel.id, key=idempotency_key)
        if existing is not None:
            # Replayed request: return the original booking (hash checked on store).
            if existing.request_hash != _request_hash(payload):
                from minirail.utils.exc import IdempotencyConflictException

                raise IdempotencyConflictException("Idempotency-Key was reused with a different request body")
            return BookingFetcher(session).get_by_key_or_raise(existing.booking_key)

    booking = CreateBookingJob(
        session=session,
        sales_channel_id=sales_channel.id,
        od_id=payload.od_id,
        passengers=payload.passengers,
        discount_code=payload.discount_code,
    ).call_for_api()

    ttl_ms = get_app().configuration.api.booking_ttl_seconds * 1000
    enqueue_outbox(
        session,
        actor_name="expire_booking",
        payload={"args": [booking.id]},
        delay_ms=ttl_ms,
    )
    if idempotency_key is not None:
        store_idempotency(
            session,
            sales_channel_id=sales_channel.id,
            key=idempotency_key,
            request_hash=_request_hash(payload),
            booking_key=booking.booking_key,
        )
    session.commit()

    with get_session() as publish_session:
        publish_pending_outbox(publish_session)
        publish_session.commit()

    TripSearchFetcher.expire()
    return BookingFetcher(session).get_by_key_or_raise(booking.booking_key)


@router.get("/{booking_key}")
def get_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    booking_key: str,
) -> BookingOutputSchema:
    return BookingFetcher(session).get_by_key_or_raise(booking_key)


@router.post("/{booking_key}/confirm")
def confirm_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    booking_key: str,
    payload: BookingConfirmSchema,
) -> BookingOutputSchema:
    # Phase 1 — claim inside a short transaction (no PSP call while locks held).
    claimed = ClaimConfirmBookingJob(session=session, booking_key=booking_key).call_for_api()
    amount = claimed.total_amount
    currency = claimed.currency
    session.commit()

    # Phase 2 — charge outside any database transaction.
    result = payments.charge(payload.payment_token, amount, currency)

    # Phase 3 — finalize or abort in a fresh transaction.
    with get_session() as finalize_session:
        if not result.success:
            AbortConfirmBookingJob(session=finalize_session, booking_key=booking_key).call_for_api()
            finalize_session.commit()
            raise PaymentDeclinedException(f"Payment declined ({result.failure_reason})")
        FinalizeConfirmBookingJob(session=finalize_session, booking_key=booking_key).call_for_api()
        finalize_session.commit()

    send_booking_notification.send(claimed.id, "booking.confirmed")
    with get_session() as read_session:
        return BookingFetcher(read_session).get_by_key_or_raise(booking_key)


@router.post("/{booking_key}/cancel")
def cancel_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    booking_key: str,
) -> BookingOutputSchema:
    booking = CancelBookingJob(session=session, booking_key=booking_key).call_for_api()
    session.commit()

    send_booking_notification.send(booking.id, "booking.cancelled")
    TripSearchFetcher.expire()  # seats came back
    return BookingFetcher(session).get_by_key_or_raise(booking_key)
