"""Fake payment gateway.

Stands in for an external PSP so the project runs fully offline. It behaves
like the real thing where it matters: it takes wall-clock time (a network
round-trip), and it can decline.
"""

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

# Any other token is accepted.
DECLINED_TOKEN = "tok_declined"  # noqa: S105 - not a secret, a gateway test token

_SIMULATED_LATENCY_SECONDS = 0.05


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    transaction_reference: str | None = None
    failure_reason: str | None = None


def charge(payment_token: str, amount: Decimal, currency: str) -> PaymentResult:
    time.sleep(_SIMULATED_LATENCY_SECONDS)  # simulated network round-trip
    if payment_token == DECLINED_TOKEN:
        return PaymentResult(success=False, failure_reason="card_declined")
    return PaymentResult(success=True, transaction_reference=f"pay_{uuid.uuid4().hex[:12]}")
