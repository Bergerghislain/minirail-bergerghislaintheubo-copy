from collections.abc import Iterator

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from minirail.utils.app import get_app, get_session
from minirail.utils.exc import ErrorCodeEnum, MinirailException
from minirail.utils.schema import ProblemSchema, Schema


def session_transaction() -> Iterator[Session]:
    """FastAPI dependency providing the request's database session.

    The session never auto-commits: an endpoint that writes must call
    session.commit() itself, once, when its unit of work is complete.
    """
    with get_session() as session:
        yield session


healthcheck_router = APIRouter(prefix="/api/healthcheck", tags=["healthcheck"])


class HealthCheckSchema(Schema):
    status: str
    services: dict[str, str]


@healthcheck_router.get("/ping")
def ping() -> dict[str, str]:
    """Liveness: the process is up. Checks nothing else — must stay cheap."""
    return {"status": "ok"}


@healthcheck_router.get("/deep", responses={503: {"model": HealthCheckSchema}})
def deep_check(response: Response) -> HealthCheckSchema:
    """Readiness: the process can actually serve traffic (database + redis)."""
    app = get_app()
    services: dict[str, str] = {}
    try:
        with app.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception:
        app.logger.exception("Healthcheck: postgres unreachable")
        services["postgres"] = "unreachable"
    try:
        app.redis.ping()
        services["redis"] = "ok"
    except Exception:
        app.logger.exception("Healthcheck: redis unreachable")
        services["redis"] = "unreachable"

    healthy = all(state == "ok" for state in services.values())
    if not healthy:
        response.status_code = 503
    return HealthCheckSchema(status="ok" if healthy else "degraded", services=services)


def _handle_business_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, MinirailException):
        raise exc  # not ours to handle
    problem = ProblemSchema(error_code=exc.error_code, message=exc.message)
    return JSONResponse(status_code=exc.http_status_code, content=problem.model_dump(by_alias=True))


def register_exception_handlers(asgi_app: FastAPI) -> None:
    asgi_app.add_exception_handler(MinirailException, _handle_business_exception)


__all__ = [
    "ErrorCodeEnum",
    "Schema",
    "healthcheck_router",
    "register_exception_handlers",
    "session_transaction",
]
