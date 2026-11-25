"""Real PostgreSQL concurrency: two connections racing on the last discount use.

Bypasses the savepoint test harness so FOR UPDATE actually serializes across
independent transactions — the rolled-back outer transaction cannot do that.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from minirail.inventory.models import OD, Station
from minirail.sales.jobs.create_booking import CreateBookingJob
from minirail.sales.models import Booking, DiscountCode, SalesChannel
from minirail.sales.schemas.booking import PassengerInputSchema
from minirail.sales.service.discount_code import normalize_discount_code
from minirail.utils.app import App
from minirail.utils.exc import DiscountCodeExhaustedException
from tests.helpers import build_service_with_ods


def test_concurrent_last_discount_use_is_serialized(test_app: App) -> None:
    """Exactly one of two concurrent bookings may consume the final use."""
    suffix = uuid.uuid4().hex[:4].upper()
    code = normalize_discount_code(f"L{suffix}USE")
    real_session_factory = sessionmaker(bind=test_app.engine)

    with real_session_factory() as setup:
        service = build_service_with_ods(
            setup,
            station_codes=[f"A{suffix}", f"B{suffix}"],
            seat_capacity=6,
            price_per_leg=Decimal("40.00"),
        )
        origin = setup.scalars(select(Station).where(Station.code == f"A{suffix}")).one()
        destination = setup.scalars(select(Station).where(Station.code == f"B{suffix}")).one()
        od = setup.scalars(
            select(OD).where(
                OD.service_id == service.id,
                OD.origin_station_id == origin.id,
                OD.destination_station_id == destination.id,
            )
        ).one()
        channel = SalesChannel(name=f"race-{suffix}", api_key=f"race-key-{suffix}")
        setup.add(channel)
        setup.flush()
        discount = DiscountCode(
            sales_channel=channel,
            code=code,
            percent_off=10,
            max_uses=1,
            use_count=0,
            is_active=True,
        )
        setup.add(discount)
        setup.commit()
        channel_id = channel.id
        od_id = od.id
        discount_id = discount.id

    barrier = threading.Barrier(2)

    def attempt_booking() -> str:
        barrier.wait(timeout=10)
        with real_session_factory() as worker:
            try:
                CreateBookingJob(
                    session=worker,
                    sales_channel_id=channel_id,
                    od_id=od_id,
                    passengers=[PassengerInputSchema(first_name="Race", last_name="Condition")],
                    discount_code=code,
                ).call_for_api()
                worker.commit()
                return "ok"
            except DiscountCodeExhaustedException:
                worker.rollback()
                return "exhausted"
            except Exception:
                worker.rollback()
                raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt_booking) for _ in range(2)]
        outcomes = [future.result(timeout=30) for future in futures]

    assert sorted(outcomes) == ["exhausted", "ok"], outcomes

    with real_session_factory() as verify:
        assert verify.get_one(DiscountCode, discount_id).use_count == 1
        booked = verify.scalars(select(Booking).where(Booking.discount_code_id == discount_id)).all()
        assert len(booked) == 1
        assert booked[0].discount_amount == Decimal("4.00")
        assert booked[0].total_amount == Decimal("36.00")
