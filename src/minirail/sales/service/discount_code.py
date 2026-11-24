"""Discount-code data primitives: look up, reserve a use, release a use.

Everything here flushes and never commits — the caller owns the transaction.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import DiscountCode
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import DiscountCodeExhaustedException, InvalidDiscountCodeException

_MONEY = Decimal("0.01")


def get_discount_code_for_update(
    session: MinirailSession,
    *,
    code: str,
    sales_channel_id: int,
) -> DiscountCode:
    """Load a discount code for this sales channel, locking the row.

    The FOR UPDATE lock makes concurrent bookings serialize on this code so
    ``use_count`` cannot race past ``max_uses``.
    """
    statement = (
        select(DiscountCode)
        .where(
            DiscountCode.code == code.strip().upper(),
            DiscountCode.sales_channel_id == sales_channel_id,
        )
        .with_for_update()
    )
    discount = session.scalars(statement).one_or_none()
    if discount is None or not discount.is_active:
        raise InvalidDiscountCodeException(f"Discount code {code!r} is not valid for this sales channel")
    if discount.valid_until is not None and discount.valid_until <= utc_now():
        raise InvalidDiscountCodeException(f"Discount code {code!r} is no longer valid")
    if discount.use_count >= discount.max_uses:
        raise DiscountCodeExhaustedException(f"Discount code {code!r} has no remaining uses")
    return discount


def compute_discount_amount(*, full_amount: Decimal, percent_off: Decimal) -> Decimal:
    """Return how much to subtract from ``full_amount`` (rounded to cents)."""
    raw = full_amount * (percent_off / Decimal("100"))
    return raw.quantize(_MONEY, rounding=ROUND_HALF_UP)


def reserve_discount_use(session: MinirailSession, discount: DiscountCode) -> None:
    """Consume one use. Caller must have loaded the row with FOR UPDATE."""
    if discount.use_count >= discount.max_uses:
        raise DiscountCodeExhaustedException(f"Discount code {discount.code!r} has no remaining uses")
    discount.use_count += 1
    session.flush()


def release_discount_use(session: MinirailSession, discount: DiscountCode) -> None:
    """Give one use back (PENDING booking cancelled or expired)."""
    if discount.use_count > 0:
        discount.use_count -= 1
        session.flush()
