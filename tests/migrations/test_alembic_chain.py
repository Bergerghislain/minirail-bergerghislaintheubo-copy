"""Prove the Alembic chain applies on an empty database and matches models.

The main suite builds the schema from metadata; a forgotten migration would
never fail there. This module uses a dedicated database and the real upgrade
path, then asks Alembic whether models still match.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DATABASE = "minirail_migrations_test"


def _admin_dsn() -> str:
    from minirail.utils.config import load_configuration

    return load_configuration().database.dsn


def _migration_dsn() -> str:
    base, _, _ = _admin_dsn().rpartition("/")
    return f"{base}/{MIGRATION_DATABASE}"


@pytest.fixture(scope="module")
def migration_database() -> Generator[str]:
    admin = create_engine(_admin_dsn(), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DATABASE} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {MIGRATION_DATABASE}"))
    admin.dispose()
    yield _migration_dsn()
    admin = create_engine(_admin_dsn(), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DATABASE} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def alembic_config(migration_database: str) -> Generator[Config]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", migration_database)
    previous = os.environ.get("MINIRAIL_DB_DSN")
    # env.py reads the app config; point it at the dedicated migration DB.
    os.environ["MINIRAIL_DB_DSN"] = migration_database
    yield config
    if previous is None:
        os.environ.pop("MINIRAIL_DB_DSN", None)
    else:
        os.environ["MINIRAIL_DB_DSN"] = previous


def test_alembic_upgrade_head_and_check(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    # Fails if models have columns/constraints not reflected in migrations.
    command.check(alembic_config)


def test_alembic_downgrade_and_reupgrade(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "-1")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
