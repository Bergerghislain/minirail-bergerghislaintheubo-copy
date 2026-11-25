from enum import StrEnum, auto
from typing import ClassVar


class ErrorCodeEnum(StrEnum):
    """Stable, machine-readable error identifiers exposed in API payloads.

    Keep alphabetically sorted.
    """

    BOOKING_NOT_PENDING = auto()
    DISCOUNT_CODE_EXHAUSTED = auto()
    DISCOUNT_NOT_APPLICABLE = auto()
    IDEMPOTENCY_KEY_CONFLICT = auto()
    INTERNAL_ERROR = auto()
    INVALID_API_KEY = auto()
    INVALID_DISCOUNT_CODE = auto()
    ITEM_NOT_FOUND = auto()
    PAYMENT_DECLINED = auto()
    SERVICE_UNAVAILABLE = auto()
    SOLD_OUT = auto()
    VALIDATION_ERROR = auto()


class MinirailException(Exception):
    """Base class for business exceptions.

    Subclasses declare how they translate to HTTP: the API exception handler
    (see minirail.utils.api) maps any raised MinirailException to a structured
    JSON problem with `http_status_code` and `error_code`. Exceptions that are
    NOT MinirailException are bugs and surface as opaque 500s.
    """

    http_status_code: ClassVar[int] = 500
    error_code: ClassVar[ErrorCodeEnum] = ErrorCodeEnum.INTERNAL_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ItemNotFoundException(MinirailException):
    http_status_code = 404
    error_code = ErrorCodeEnum.ITEM_NOT_FOUND


class SoldOutException(MinirailException):
    http_status_code = 409
    error_code = ErrorCodeEnum.SOLD_OUT


class BookingNotPendingException(MinirailException):
    http_status_code = 409
    error_code = ErrorCodeEnum.BOOKING_NOT_PENDING


class PaymentDeclinedException(MinirailException):
    http_status_code = 409
    error_code = ErrorCodeEnum.PAYMENT_DECLINED


class InvalidAPIKeyException(MinirailException):
    http_status_code = 401
    error_code = ErrorCodeEnum.INVALID_API_KEY


class ServiceUnavailableException(MinirailException):
    http_status_code = 503
    error_code = ErrorCodeEnum.SERVICE_UNAVAILABLE


class InvalidDiscountCodeException(MinirailException):
    """Unknown, inactive, expired, or belonging to another sales channel.

    These cases share one public error code so a client cannot probe whether
    a code exists on a different partner.
    """

    http_status_code = 400
    error_code = ErrorCodeEnum.INVALID_DISCOUNT_CODE


class DiscountCodeExhaustedException(MinirailException):
    http_status_code = 409
    error_code = ErrorCodeEnum.DISCOUNT_CODE_EXHAUSTED


class DiscountNotApplicableException(MinirailException):
    http_status_code = 400
    error_code = ErrorCodeEnum.DISCOUNT_NOT_APPLICABLE


class IdempotencyKeyConflictException(MinirailException):
    """Same Idempotency-Key reused with a different request body."""

    http_status_code = 409
    error_code = ErrorCodeEnum.IDEMPOTENCY_KEY_CONFLICT
