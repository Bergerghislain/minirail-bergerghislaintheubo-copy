import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger("minirail")

CONFIG_ENV_VAR = "MINIRAIL_CONFIG"
DB_DSN_ENV_VAR = "MINIRAIL_DB_DSN"
REDIS_DSN_ENV_VAR = "MINIRAIL_REDIS_DSN"


class DatabaseConfig(BaseModel):
    dsn: str


class RedisConfig(BaseModel):
    dsn: str


class BrokerConfig(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _strip_sqlalchemy_driver(cls, value: str) -> str:
        # Remoulade passes this URL both to SQLAlchemy AND to raw
        # psycopg.connect() (for LISTEN/NOTIFY); psycopg rejects the
        # SQLAlchemy "+driver" dialect suffix, so normalize it away.
        return value.replace("postgresql+psycopg://", "postgresql://", 1)


class ApiConfig(BaseModel):
    booking_ttl_seconds: int = 900
    # Minimum booking total a discount code may be applied to. The same
    # threshold applies to every booking, whatever the code; it is copied onto
    # the booking at creation so past sales keep the rule they were sold under.
    discount_min_price: Decimal = Decimal("0.00")


class Configuration(BaseModel):
    database: DatabaseConfig
    redis: RedisConfig
    broker: BrokerConfig
    api: ApiConfig = ApiConfig()


def _find_configuration_file() -> Path | None:
    """Resolution order: $MINIRAIL_CONFIG > ./configuration.yaml > ./configuration_example.yaml.

    The example file is a complete, working local configuration, so a fresh
    clone runs with zero manual setup; create `configuration.yaml` only to
    override it.
    """
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path is not None:
        path = Path(env_path)
        if not path.exists():
            raise FileNotFoundError(f"{CONFIG_ENV_VAR} points at {path}, which does not exist")
        return path
    for candidate in (Path("configuration.yaml"), Path("configuration_example.yaml")):
        if candidate.exists():
            if candidate.name == "configuration_example.yaml":
                logger.info("No configuration.yaml found, falling back to %s", candidate)
            return candidate
    return None


def load_configuration() -> Configuration:
    path = _find_configuration_file()
    raw: dict[str, Any] = {}
    if path is not None:
        with path.open() as f:
            raw = yaml.safe_load(f) or {}
    # Environment overrides (used by CI, where no YAML file exists).
    db_dsn = os.environ.get(DB_DSN_ENV_VAR)
    redis_dsn = os.environ.get(REDIS_DSN_ENV_VAR)
    if db_dsn is not None:
        raw.setdefault("database", {})["dsn"] = db_dsn
        # The broker shares the main database unless configured otherwise.
        raw.setdefault("broker", {}).setdefault("url", db_dsn)
    if redis_dsn is not None:
        raw.setdefault("redis", {})["dsn"] = redis_dsn
    if not raw:
        raise FileNotFoundError(
            "No configuration found: run from the project root (where configuration_example.yaml lives), "
            f"or set {CONFIG_ENV_VAR}, or set {DB_DSN_ENV_VAR} and {REDIS_DSN_ENV_VAR}"
        )
    return Configuration.model_validate(raw)
