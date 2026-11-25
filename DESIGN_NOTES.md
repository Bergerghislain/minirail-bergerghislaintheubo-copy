# Design notes — discount codes

## Scope

Percent-off promo codes owned by a sales channel, applied at booking creation only.

- Model: `DiscountCode` (FK `sales_channel`, unique `(sales_channel_id, code)`, codes stored uppercase).
- Optional `discountCode` on `POST /api/bookings/` → response `discountAmount` + `discountCode`.
- Discount adjusts **booking `total_amount` only**; ticket `price_at_sale` stays the OD list price.
- Admin: CLI `minirail create-discount-code` (no REST admin). Demo seed: `SAVE10` (10%, 100 uses).
- Money: `Decimal`, cents with `ROUND_HALF_UP`. Services/jobs flush; API/CLI commit.

## Decisions

1. **Reserve at PENDING create** (same TX as seat hold), not at confirm — otherwise concurrent holds can overshoot `max_uses` after payment.
2. **Release vs keep**: cancel/expire of **PENDING** returns the use; **CONFIRMED** then cancel **keeps** it (promo already applied to a paid sale).
3. **`SELECT … FOR UPDATE`** on the code row before the quota check (lock order: seats, then code).
4. **`min_price` on `Booking`**, not on `DiscountCode` — company-wide floor from `api.discount_min_price`, snapshotted at sale (same idea as `price_at_sale`).
5. **Error contract** (opaque on purpose for cross-channel probing):
   - unknown / inactive / expired / other channel → `invalid_discount_code` (400)
   - `use_count >= max_uses` → `discount_code_exhausted` (409)
   - gross total `< min_price` → `discount_not_applicable` (400)
6. **Journal `discount_redemption`**: RESERVED → RELEASED | CONSUMED; `use_count` stays the fast quota. Release/consume via atomic `UPDATE … WHERE status = RESERVED`.
7. **Optional `Idempotency-Key`** on `POST /api/bookings/` (per sales channel): same key + same body → replay same booking (no duplicate side effects); same key + different body → `idempotency_key_conflict` (409).
8. **Transactional outbox** for `expire_booking`: row written in the same TX as the PENDING booking; remoulade publish happens in a post-commit drain. Avoids enqueueing a message for a booking that never committed.

   **Limit without a periodic drain:** if the process dies after the booking+outbox commit but before drain, the row stays `published_at IS NULL` until something drains again (today: the next successful create, or seed). Seats are still recoverable via `expire-stale-bookings`; the delayed actor path for that booking stays idle until then.
9. **Auth cache TTL** from `api.auth_cache_ttl_seconds` (~60s); soft per-channel rate limit (`api.rate_limit_per_minute`) — over-limit still served, headers only. `GET /api/trips/search` stays a JSON array (`response[0].odId`); optional `limit`/`offset` slice only, never a page wrapper.

## Out of scope

- Fixed-amount, stacking, per-passenger discounts
- Attach a code to an already-created booking
- Admin REST; soft-delete of codes
- Rewriting ticket prices; complex refunds; caching discount reads

## Try it

```bash
make up && make migrate && make seed && make serve
# worker in another terminal: make worker

curl -H "X-API-Key: demo-channel-key" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/api/bookings/ \
  -d '{"odId": <odId>, "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}], "discountCode": "SAVE10"}'
```
