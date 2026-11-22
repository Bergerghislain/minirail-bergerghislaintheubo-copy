from enum import StrEnum, auto
from typing import ClassVar


class ErrorCodeEnum(StrEnum):
    """Stable, machine-readable error identifiers exposed in API payloads.

    Keep alphabetically sorted.
    """

    BOOKING_NOT_PENDING = auto()
    DISCOUNT_CODE_EXHAUSTED = auto()
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


class InvalidDiscountCodeException(MinirailException):
    """Unknown, inactive, or not belonging to the caller's sales channel."""

    http_status_code = 400
    error_code = ErrorCodeEnum.INVALID_DISCOUNT_CODE


class DiscountCodeExhaustedException(MinirailException):
    """The partner-agreed max_uses has been reached."""

    http_status_code = 409
    error_code = ErrorCodeEnum.DISCOUNT_CODE_EXHAUSTED


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
