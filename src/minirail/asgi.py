from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import remoulade
from fastapi import FastAPI

import minirail
from minirail.inventory.api import stations, trips
from minirail.sales.api import bookings
from minirail.utils.api import healthcheck_router, register_exception_handlers
from minirail.utils.broker import init_broker


@asynccontextmanager
async def _lifespan(asgi_app: FastAPI) -> AsyncGenerator[None]:
    # The API enqueues background messages (booking expiry, notifications),
    # so it needs a broker too. Tests install their own broker beforehand.
    if remoulade.broker.global_broker is None:
        init_broker()
    yield


def create_asgi_app() -> FastAPI:
    asgi_app = FastAPI(
        title="Minirail",
        version=minirail.__version__,
        description="A mini rail reservation backend: seat inventory + bookings.",
        lifespan=_lifespan,
    )
    register_exception_handlers(asgi_app)
    asgi_app.include_router(healthcheck_router)
    asgi_app.include_router(stations.router)
    asgi_app.include_router(trips.router)
    asgi_app.include_router(bookings.router)
    return asgi_app


# Import target for uvicorn ("minirail.asgi:app").
app = create_asgi_app()
