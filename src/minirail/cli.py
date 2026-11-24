import logging
import secrets
import signal
import time
from datetime import UTC, datetime
from decimal import Decimal
from types import FrameType

import click
import uvicorn


def _register_sigterm() -> None:
    """Map SIGTERM to KeyboardInterrupt so `finally` blocks and context
    managers run on shutdown — Kubernetes stops pods with SIGTERM."""

    def _raise_keyboard_interrupt(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)


@click.group()
def cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _register_sigterm()


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (development only).")
def serve(host: str, port: int, reload: bool) -> None:
    """Run the API server."""
    uvicorn.run("minirail.asgi:app", host=host, port=port, reload=reload)


@cli.command()
@click.option("--threads", default=4, show_default=True, help="Worker thread count.")
def worker(threads: int) -> None:
    """Run the background worker (booking expiry, notifications)."""
    import remoulade
    from remoulade import Worker

    from minirail.utils.broker import init_broker

    init_broker()
    remoulade_worker = Worker(remoulade.get_broker(), worker_threads=threads)
    remoulade_worker.start()
    click.echo(f"Worker running with {threads} threads, press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("Stopping worker...")
        remoulade_worker.stop()


@cli.command("expire-stale-bookings")
def expire_stale_bookings() -> None:
    """Expire overdue PENDING bookings now.

    Ops fallback: normally the delayed worker messages handle expiry; this
    sweep catches bookings whose message was lost (e.g. broker wiped).
    """
    from minirail.inventory.fetcher.trip_search import TripSearchFetcher
    from minirail.sales.jobs.expire_booking import ExpireBookingJob, find_stale_booking_ids
    from minirail.utils.app import get_session

    expired_count = 0
    with get_session() as session:
        for booking_id in find_stale_booking_ids(session):
            result = ExpireBookingJob(session=session, booking_id=booking_id).call()
            if result.output:
                expired_count += 1
        session.commit()
    if expired_count:
        TripSearchFetcher.expire()
    click.echo(f"Expired {expired_count} booking(s)")


@cli.command("init-demo-data")
@click.option("--force", is_flag=True, help="Recreate the demo dataset even if it already exists (wipes ALL data).")
def init_demo_data(force: bool) -> None:
    """Load the demo dataset: stations, routes, 14 days of services, a sales
    channel, and two sample bookings."""
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    from minirail.demo_data import create_demo_data, demo_data_exists
    from minirail.orm import Base
    from minirail.utils.app import get_session

    try:
        with get_session() as session:
            if demo_data_exists(session):
                if not force:
                    click.echo("Demo data already present (station FRPAR exists). Use --force to wipe and recreate.")
                    raise SystemExit(0)
                # Truncate through THIS session: the check above is still
                # reading these tables in this transaction, and a TRUNCATE
                # from a second connection would wait on it forever.
                table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
                session.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
            summary = create_demo_data(session)
            session.commit()
    except ProgrammingError as exc:
        raise click.ClickException(
            f"Database schema missing or out of date — did you run 'make migrate' first? ({exc.orig})"
        ) from exc

    date_str = summary.first_date.isoformat()
    click.echo(f"Seeded {summary.service_count} services starting {date_str}.")
    click.echo(f"API key: {summary.api_key}")
    click.echo(f"Discount code: {summary.discount_code} (10% off, 100 uses)")
    click.echo(f"Confirmed sample booking: {summary.confirmed_booking_key}")
    click.echo(f"Pending sample booking:   {summary.pending_booking_key} (expires in 15 min)")
    click.echo("\nTry it:")
    click.echo(
        f'  curl -H "X-API-Key: {summary.api_key}" "http://127.0.0.1:8000/api/trips/search'
        f'?originStationCode=FRPAR&destinationStationCode=FRMRS&date={date_str}"'
    )


@cli.command("create-sales-channel")
@click.argument("name")
def create_sales_channel(name: str) -> None:
    """Create a sales channel and print its API key."""
    from minirail.orm import load_model_registry
    from minirail.sales.models import SalesChannel
    from minirail.utils.app import get_session

    load_model_registry()

    api_key = secrets.token_urlsafe(24)
    with get_session() as session:
        session.add(SalesChannel(name=name, api_key=api_key))
        session.commit()
    click.echo(f"Sales channel {name!r} created, API key: {api_key}")


@cli.command("create-discount-code")
@click.argument("sales_channel_name")
@click.argument("code")
@click.option("--percent-off", required=True, type=click.STRING, help="Percentage off, e.g. 10 for 10%.")
@click.option("--max-uses", required=True, type=click.INT, help="How many bookings may use the code.")
@click.option("--valid-until", type=click.DateTime(), help="Last moment the code may be used (UTC).")
def create_discount_code(
    sales_channel_name: str, code: str, percent_off: str, max_uses: int, valid_until: datetime | None
) -> None:
    """Create a discount code for an existing sales channel."""
    from sqlalchemy import select

    from minirail.orm import load_model_registry
    from minirail.sales.models import DiscountCode, SalesChannel
    from minirail.sales.service.discount_code import normalize_code
    from minirail.utils.app import get_session

    load_model_registry()
    # Parsed from the string option: Decimal(float) would store 10.000000000000000555.
    percentage = Decimal(percent_off)
    if percentage <= 0 or percentage > 100:
        raise click.ClickException("--percent-off must be above 0 and at most 100")
    if max_uses < 1:
        raise click.ClickException("--max-uses must be at least 1")

    normalized = normalize_code(code)
    with get_session() as session:
        channel = session.scalars(select(SalesChannel).where(SalesChannel.name == sales_channel_name)).one_or_none()
        if channel is None:
            raise click.ClickException(f"Unknown sales channel {sales_channel_name!r}")
        session.add(
            DiscountCode(
                sales_channel_id=channel.id,
                code=normalized,
                percent_off=percentage,
                max_uses=max_uses,
                valid_until=valid_until.replace(tzinfo=UTC) if valid_until is not None else None,
            )
        )
        session.commit()
    click.echo(f"Discount code {normalized!r} created for {sales_channel_name!r}: {percentage}% off, {max_uses} uses")
