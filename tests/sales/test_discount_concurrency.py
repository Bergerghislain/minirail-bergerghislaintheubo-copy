"""Real concurrency test outside the rolled-back harness.

The main suite shares one connection with savepoints, so FOR UPDATE cannot
prove serialization. This module opens two independent connections on the
session-scoped test engine and races two reserves on the same code.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from minirail.sales.models import Booking, DiscountCode, SalesChannel
from minirail.sales.service.discount_code import get_valid_discount_code_for_update, reserve_discount_use
from minirail.utils.app import App
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import DiscountCodeExhaustedException


@pytest.fixture
def committed_channel_and_code(test_app: App) -> Generator[tuple[int, int, str]]:
    """Insert a channel + one-use code with real commits (visible to other connections).

    Tears down committed rows afterwards so other tests that scan the whole
    table (e.g. stale-booking sweeps) are not polluted.
    """
    suffix = uuid.uuid4().hex[:8]
    factory = sessionmaker(bind=test_app.engine)
    with factory() as session:
        channel = SalesChannel(name=f"concurrency-{suffix}", api_key=f"concurrency-key-{suffix}")
        session.add(channel)
        session.flush()
        code = DiscountCode(
            sales_channel_id=channel.id,
            code="ONCE",
            percent_off=Decimal("10.00"),
            max_uses=1,
            use_count=0,
        )
        session.add(code)
        session.commit()
        channel_id, code_id = channel.id, code.id
    yield channel_id, code_id, "ONCE"
    with factory() as session:
        from sqlalchemy import delete

        from minirail.sales.models import DiscountRedemption

        session.execute(delete(DiscountRedemption).where(DiscountRedemption.discount_code_id == code_id))
        session.execute(delete(Booking).where(Booking.sales_channel_id == channel_id))
        session.execute(delete(DiscountCode).where(DiscountCode.id == code_id))
        session.execute(delete(SalesChannel).where(SalesChannel.id == channel_id))
        session.commit()


def _reserve_once(
    engine: Engine,
    channel_id: int,
    code_id: int,
    code_value: str,
    results: list[str],
    lock: threading.Barrier,
) -> None:
    factory = sessionmaker(bind=engine)
    with factory() as session:
        booking = Booking(
            sales_channel_id=channel_id,
            total_amount=Decimal("45.00"),
            expires_at=utc_now(),
        )
        session.add(booking)
        session.flush()
        lock.wait()
        try:
            discount = get_valid_discount_code_for_update(session, code=code_value, sales_channel_id=channel_id)
            assert discount.id == code_id
            reserve_discount_use(session, discount, booking)
            session.commit()
            results.append("ok")
        except DiscountCodeExhaustedException:
            session.rollback()
            results.append("exhausted")
        except Exception as exc:
            session.rollback()
            results.append(f"error:{type(exc).__name__}:{exc}")


def test_two_connections_cannot_both_reserve_the_last_use(
    test_app: App, committed_channel_and_code: tuple[int, int, str]
) -> None:
    channel_id, code_id, code_value = committed_channel_and_code
    results: list[str] = []
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(
            target=_reserve_once,
            args=(test_app.engine, channel_id, code_id, code_value, results, barrier),
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results) == ["exhausted", "ok"]

    factory = sessionmaker(bind=test_app.engine)
    with factory() as session:
        code = session.get(DiscountCode, code_id)
        assert code is not None
        assert code.use_count == 1
