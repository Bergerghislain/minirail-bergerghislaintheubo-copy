"""Transactional outbox primitives.

Enqueue inside the business transaction; publish after commit. Never commits.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update

from minirail.orm import MinirailSession
from minirail.sales.models import OutboxMessage
from minirail.utils.date_utils import utc_now


def enqueue_outbox(
    session: MinirailSession,
    *,
    actor_name: str,
    payload: dict[str, Any],
    delay_ms: int = 0,
) -> OutboxMessage:
    message = OutboxMessage(actor_name=actor_name, payload=payload, delay_ms=delay_ms)
    session.add(message)
    session.flush()
    return message


def fetch_unpublished(session: MinirailSession, *, limit: int = 100) -> Sequence[OutboxMessage]:
    statement = (
        select(OutboxMessage)
        .where(OutboxMessage.published_at.is_(None))
        .order_by(OutboxMessage.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(session.scalars(statement).all())


def mark_published(session: MinirailSession, message_ids: Sequence[int]) -> None:
    if not message_ids:
        return
    session.execute(
        update(OutboxMessage)
        .where(OutboxMessage.id.in_(message_ids), OutboxMessage.published_at.is_(None))
        .values(published_at=utc_now())
    )
    session.flush()


def publish_pending_outbox(session: MinirailSession) -> int:
    """Deliver unpublished outbox rows to Remoulade and mark them published.

    Called by the API (or an ops sweep) after the business transaction has
    committed. The publish+mark step is its own short transaction owned by the
    caller.
    """
    from minirail.sales.actors.booking_expiry import expire_booking

    actors = {
        "expire_booking": expire_booking,
    }
    pending = fetch_unpublished(session)
    published_ids: list[int] = []
    for message in pending:
        actor = actors.get(message.actor_name)
        if actor is None:
            continue
        args = tuple(message.payload.get("args", ()))
        actor.send_with_options(args=args, delay=message.delay_ms)
        published_ids.append(message.id)
    mark_published(session, published_ids)
    return len(published_ids)
