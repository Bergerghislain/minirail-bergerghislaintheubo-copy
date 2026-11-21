import remoulade

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.sales.jobs.expire_booking import ExpireBookingJob
from minirail.utils.app import get_app, get_session


@remoulade.actor
def expire_booking(booking_id: int) -> None:
    """Fires booking_ttl_seconds after each booking's creation.

    Most firings are no-ops: the booking was confirmed or cancelled in time
    and ExpireBookingJob's status guard leaves it alone. The actor owns the
    transaction: it commits, then invalidates the availability cache — in
    that order, so the cache is never refilled from uncommitted state.
    """
    with get_session() as session:
        result = ExpireBookingJob(session=session, booking_id=booking_id).call()
        session.commit()
    if result.output:
        TripSearchFetcher.expire()
        get_app().logger.info("Booking %s expired, seats released", booking_id)
