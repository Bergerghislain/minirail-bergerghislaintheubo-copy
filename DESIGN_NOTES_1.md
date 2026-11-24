# Design notes — discount codes

## Scope we settled on

Sales channels can create percent-off promo codes and pass them when booking.

- A code belongs to **one sales channel** (partner).
- It has a **percent off** (e.g. 10%) and a hard **max_uses** limit.
- It is valid until an optional `valid_until` date, and can be paused at any
  time with `is_active`.
- A booking total below a **minimum price** cannot use a code. The threshold is
  the same for every booking, so it is a configuration setting
  (`api.discount_min_price`), copied onto the booking as `min_price`.
- The client sends optional `discountCode` on `POST /api/bookings/`, in any
  casing.
- The booking response shows `discountAmount` and the applied `discountCode`.
- Codes are created via CLI: `minirail create-discount-code CHANNEL CODE --percent-off 10 --max-uses 100 [--valid-until 2026-12-31]`.
- Demo seed includes `SAVE10` (10% off, 100 uses).

## Decisions that mattered

1. **Percent-off only** (not fixed amount). Simple to understand and enough for
   a first version: no currency on the code, and no total that could go
   negative.
2. **Reserve a use at booking creation** (PENDING), not at confirmation.
   Otherwise several people could hold seats with the same almost-exhausted
   code and overshoot `max_uses` after payment.
3. **Release the use** if the PENDING booking is cancelled or expires (payment
   never came). If the booking was confirmed then later cancelled, we **keep**
   the use consumed — the promo already applied to a paid sale.
4. **Row lock (`FOR UPDATE`)** when reading the code so two concurrent bookings
   cannot both pass the `use_count < max_uses` check. Seats are locked first,
   then the code: one order for everyone, so no deadlock, and the contended row
   is held for as little time as possible.
5. **Releasing a use is a single atomic `UPDATE`**, not a counter computed in
   Python. Cancel and expiry start from a booking and hold no lock, so
   subtracting from a value read earlier would overwrite a use another booking
   reserved in the meantime.
6. **Uniqueness is per partner** (`sales_channel_id`, `code`), not global. A
   code belongs to a partner, and the API key already isolates channels from
   each other; two partners may both want "SAVE10".
7. **`is_active` alongside `valid_until`.** `valid_until` is a planned end of
   campaign; `is_active` is an immediate, reversible kill switch for a leaked or
   misconfigured code. Deriving one from the other would mean rewriting business
   data to express an operational action.
8. **`min_price` lives on the booking.** The threshold is a company rule, not a
   per-promotion parameter, so it is configured once; it is frozen on each
   booking for auditability, the same reasoning as `price_at_sale` on a ticket.
   It is deliberately **not** exposed in the API response: it is an internal
   rule, not part of the partner contract.
9. **A booking below the threshold is refused, not silently charged full
   price.** The client explicitly asked for the code to apply; it can rebook
   without one.
10. **No public admin API** to create codes — CLI only, same style as
    `create-sales-channel`.
11. **Money is `Decimal` end to end.** The discount is quantized to cents with
    `ROUND_HALF_UP` before being subtracted, so the total stays an exact number
    of cents and discount + total equals the full price.

## Error contract

| Situation | HTTP | `errorCode` |
| --- | --- | --- |
| Unknown, deactivated, out of date, or another channel's code | 400 | `invalid_discount_code` |
| Code is usable but `use_count` reached `max_uses` | 409 | `discount_code_exhausted` |
| Code is usable but the booking total is below `min_price` | 400 | `discount_not_applicable` |

The first four cases share one error on purpose: telling "unknown" and
"expired" apart would let a partner probe another partner's codes.

## Out of scope (left out on purpose)

- Fixed-amount discounts, stacking several codes, per-passenger discounts
- Soft deletes / audit log of redemptions beyond `use_count`
- REST endpoints to list/manage codes
- Changing ticket `price_at_sale` when a discount applies (discount lives on the
  booking total only)
- Redis / cache invalidation around discount codes (they are not cached reads)
- Idempotency key on booking creation: replaying the request creates two
  bookings and consumes two uses, exactly as it already books two sets of seats
- `CHECK` constraints on `percent_off` and the counters: the CLI validates the
  range, the database would still accept a direct insert outside it
- A real concurrency test: the suite runs inside a single transaction, so
  proving the lock would need two connections outside the harness

## How to try it

```bash
make up && make migrate && make seed && make serve
# in another terminal: make worker

# book with the demo code
curl -H "X-API-Key: demo-channel-key" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/api/bookings/ \
  -d '{"odId": <odId>, "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}], "discountCode": "SAVE10"}'
```

## What we checked before submitting

```bash
make lint typecheck test            # 54 tests

# migrations are not covered by the suite: it builds the schema from the
# model metadata, so a missing migration would fail no test
uv run alembic upgrade head
uv run alembic check                # "No new upgrade operations detected."
uv run alembic downgrade -1 && uv run alembic upgrade head
```
