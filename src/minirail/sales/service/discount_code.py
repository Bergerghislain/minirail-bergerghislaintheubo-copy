"""Discount-code primitives: validate a code, reserve a use, release a use.

Everything here flushes and never commits — the caller owns the transaction.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update

from minirail.orm import MinirailSession
from minirail.sales.models import DiscountCode
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import (
    DiscountCodeExhaustedException,
    DiscountNotApplicableException,
    InvalidDiscountCodeException,
)

_CENT = Decimal("0.01")


def normalize_code(code: str) -> str:
    """Codes are stored uppercase; clients may send any casing."""
    return code.strip().upper()


def get_valid_discount_code_for_update(
    session: MinirailSession,
    *,
    code: str,
    sales_channel_id: int,
) -> DiscountCode:
    """Load a usable discount code of this sales channel, locking the row.

    Unknown, inactive, out-of-date and other channels' codes all raise the
    same InvalidDiscountCodeException: a caller must not be able to probe a
    partner's codes by reading our error messages apart.

    The FOR UPDATE lock makes concurrent bookings serialize on this row, so
    ``use_count`` cannot race past ``max_uses``.
    """
    statement = (
        select(DiscountCode)
        .where(
            DiscountCode.code == normalize_code(code),
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


def check_minimum_price(*, full_amount: Decimal, min_price: Decimal) -> None:
    """Refuse a discount on a booking cheaper than the agreed threshold."""
    if full_amount < min_price:
        raise DiscountNotApplicableException(
            f"A discount code needs a booking total of at least {min_price}, this one is {full_amount}"
        )


def compute_discount_amount(*, full_amount: Decimal, percent_off: Decimal) -> Decimal:
    """Return how much to subtract from ``full_amount``, rounded to cents."""
    raw = full_amount * (percent_off / Decimal("100"))
    return raw.quantize(_CENT, rounding=ROUND_HALF_UP)


def reserve_discount_use(session: MinirailSession, discount: DiscountCode) -> None:
    """Consume one use. Caller must have loaded the row with FOR UPDATE."""
    if discount.use_count >= discount.max_uses:
        raise DiscountCodeExhaustedException(f"Discount code {discount.code!r} has no remaining uses")
    discount.use_count += 1
    session.flush()


def release_discount_use(session: MinirailSession, discount: DiscountCode) -> None:
    """Give one use back (a PENDING booking was cancelled or expired).

    A single UPDATE, unlike the reserve path, which already holds the row
    lock: a counter computed in Python here could overwrite a use another
    booking reserved in the meantime.
    """
    session.execute(
        update(DiscountCode)
        .where(DiscountCode.id == discount.id, DiscountCode.use_count > 0)
        .values(use_count=DiscountCode.use_count - 1)
    )
    session.expire(discount, ["use_count"])
