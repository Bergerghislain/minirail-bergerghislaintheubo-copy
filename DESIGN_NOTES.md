# Design notes — discount codes

## Scope we settled on

Sales channels can create percent-off promo codes and pass them when booking.

- A code belongs to **one sales channel** (partner).
- It has a **percent off** (e.g. 10%) and a hard **max_uses** limit.
- The client sends optional `discountCode` on `POST /api/bookings/`.
- The booking response shows `discountAmount` and the applied `discountCode`.
- Codes are created via CLI: `minirail create-discount-code CHANNEL CODE --percent-off 10 --max-uses 100`.
- A discount Code is valid until a `valid_until` date
- There is a `min_price` to apply a discount Code
- Demo seed includes `SAVE10` (10% off, 100 uses).

## Decisions that mattered

1. **Percent-off only** (not fixed amount). Simple to understand and enough for a first version.
2. **Reserve a use at booking creation** (PENDING), not at confirmation. Otherwise several people could hold seats with the same almost-exhausted code and overshoot `max_uses` after payment.
3. **Release the use** if the PENDING booking is cancelled or expires (payment never came). If the booking was confirmed then later cancelled, we **keep** the use consumed — the promo already applied to a paid sale.
4. **Row lock (`FOR UPDATE`)** when reading the code so two concurrent bookings cannot both pass the `use_count < max_uses` check.
5. **No public admin API** to create codes — CLI only, same style as `create-sales-channel`.

## Out of scope (left out on purpose)

- Fixed-amount discounts, stacking several codes, per-passenger discounts
- Soft deletes / audit log of redemptions beyond `use_count`
- REST endpoints to list/manage codes
- Changing ticket `price_at_sale` when a discount applies (discount lives on the booking total only)
- Redis / cache invalidation around discount codes (they are not cached reads)

## How to try it

```bash
make up && make migrate && make seed && make serve
# in another terminal: make worker

# book with the demo code
curl -H "X-API-Key: demo-channel-key" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/api/bookings/ \
  -d '{"odId": <odId>, "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}], "discountCode": "SAVE10"}'
```