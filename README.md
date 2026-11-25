# Minirail

A mini rail reservation backend: seat inventory, availability search, and a
booking flow with payment and automatic expiry of unpaid bookings.

**Stack:** Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 17 · Redis ·
Alembic · [Remoulade](https://remoulade.readthedocs.io/) (task queue, on
PostgreSQL) · uv · ruff · pyright · pytest

If you are here for the technical test, read this file first, then
[ASSIGNMENT.md](ASSIGNMENT.md).

## Quickstart

Prerequisites: [Docker](https://docs.docker.com/engine/install/) (with the
compose plugin) and [uv](https://docs.astral.sh/uv/getting-started/installation/).
You don't need Python installed — uv provisions 3.14 automatically.

```bash
make up        # start PostgreSQL + Redis (docker compose)
make migrate   # apply database migrations (alembic upgrade head)
make seed      # load demo data — prints the API key and a ready-to-run curl
make serve     # run the API on http://127.0.0.1:8000
```

No configuration step is needed: without a `configuration.yaml`, the app
falls back to the committed [configuration_example.yaml](configuration_example.yaml),
which matches the compose services. Interactive API docs: http://127.0.0.1:8000/docs.

In a second terminal, run the background worker (booking expiry and
notifications are processed here):

```bash
make worker
```

## Walkthrough

Every business endpoint authenticates through the `X-API-Key` header; `make
seed` created a channel with key `demo-channel-key`.

```bash
export KEY="X-API-Key: demo-channel-key"
export DATE=$(date -d '+1 day' +%F)    # macOS: date -v+1d +%F

# 1. Search trips Paris → Marseille (a 2-leg journey via Lyon)
curl -H "$KEY" "http://127.0.0.1:8000/api/trips/search?originStationCode=FRPAR&destinationStationCode=FRMRS&date=$DATE"

# 2. Book 2 passengers on an OD from the search results (use its "odId")
curl -H "$KEY" -H "Content-Type: application/json" -X POST http://127.0.0.1:8000/api/bookings/ \
  -d '{"odId": <odId>, "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}, {"firstName": "Alan", "lastName": "Turing"}]}'
# → 201 with a PENDING booking; note its "bookingKey". Seats are now held:
#   re-run the search and watch remainingSeats drop.
# Add "discountCode": "SAVE10" to the payload for 10% off (seeded by `make seed`);
#   the response then carries "discountAmount" and "discountCode".
# Optional: send Idempotency-Key so a client retry does not create a second booking.

# 3. Confirm (pay) the booking — any token works except "tok_declined"
curl -H "$KEY" -H "Content-Type: application/json" -X POST \
  http://127.0.0.1:8000/api/bookings/<bookingKey>/confirm -d '{"paymentToken": "tok_ok"}'

# 4. Or cancel it (seats are released)
curl -H "$KEY" -X POST http://127.0.0.1:8000/api/bookings/<bookingKey>/cancel
```

A PENDING booking that is never confirmed holds its seats for
`booking_ttl_seconds` (15 minutes by default), then the worker's delayed
expiry message releases them — create a booking, keep `make worker` running,
and watch it flip to `EXPIRED`. To see it quickly, copy
`configuration_example.yaml` to `configuration.yaml` and lower
`booking_ttl_seconds`.

## Tests, lint, types

```bash
make test        # pytest against a real PostgreSQL (needs `make up`)
make lint        # ruff check + format check
make typecheck   # pyright (strict on src/)
make fmt         # auto-fix and format
```

The test harness (see [tests/conftest.py](tests/conftest.py)) recreates a
dedicated `minirail_test` database per run and isolates each test in a
rolled-back transaction. CI (`.github/workflows/ci.yml`) runs the same
checks plus a `migrations` job (`alembic upgrade head` then `alembic check`
on an empty database) against PostgreSQL + Redis, using `MINIRAIL_DB_DSN` /
`MINIRAIL_REDIS_DSN`.

## Configuration

Resolution order:

1. `$MINIRAIL_CONFIG` — explicit path to a YAML file
2. `./configuration.yaml` — your local override (gitignored)
3. `./configuration_example.yaml` — committed default, works with `make up`

`MINIRAIL_DB_DSN` and `MINIRAIL_REDIS_DSN` override the two DSNs directly —
that's how you point the app at a database somewhere else without writing any
YAML file (a CI job, for instance).

## Project layout

```
src/minirail/
├── asgi.py             # FastAPI app assembly
├── cli.py              # `minirail` CLI: serve, worker, init-demo-data, ...
├── orm.py              # Declarative base, naming conventions, UTCDateTime
├── utils/              # cross-cutting: app context, config, schemas, jobs,
│                       # fetchers, redis cache, auth, exceptions, broker
├── inventory/          # what is sold: stations, routes, services, legs, ODs
└── sales/              # how it is sold: sales channels, bookings, tickets
```

Each domain module follows the same internal layout — `api/` (thin HTTP
layer), `models/`, `schemas/`, `service/` (data primitives), `jobs/`
(business logic), `fetcher/` (read queries), `actors/` (background tasks).
The layering rules are enforced by
[tests/architecture/test_layering.py](tests/architecture/test_layering.py).

## Useful commands

| Command | What it does |
|---|---|
| `make psql` | psql shell on the dev database |
| `make redis-cli` | redis-cli shell |
| `uv run minirail expire-stale-bookings` | ops fallback: expire overdue PENDING bookings now |
| `uv run minirail create-sales-channel NAME` | create a channel, print its API key |
| `uv run minirail create-discount-code NAME CODE --percent-off 10 --max-uses 100 [--valid-until 2026-12-31]` | create a promotion code for a channel (date-only `--valid-until` = end of that UTC day; at most 2 decimal places on `--percent-off`) |
| `uv run minirail init-demo-data --force` | wipe everything and reseed |
| `uv run alembic revision --autogenerate -m "..."` | generate a migration from model changes |

## Troubleshooting

- **`make up` fails on port 15432/16379** — another local service uses the
  port; stop it or edit both `docker-compose.yaml` and your
  `configuration.yaml` copy.
- **`relation "station" does not exist`** — run `make migrate` before `make seed`.
- **API returns 503** — Redis (or PostgreSQL) is down; check `docker compose ps`.
  This is deliberate: see the rationale in [src/minirail/utils/fetcher.py](src/minirail/utils/fetcher.py).
- **Worker errors mentioning `pgmq`** — the database container predates the
  init script; `make down && make up && make migrate && make seed`.
