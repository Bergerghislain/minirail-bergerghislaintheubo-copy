from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import create_engine

# Import every model package so autogenerate sees the full metadata.
import minirail.inventory.models
import minirail.sales.models  # noqa: F401
from minirail.orm import Base
from minirail.utils.config import load_configuration

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Extension-owned objects (pg_partman / pgmq) live in the same database but
# are not part of our models. Without this filter, `alembic check` reports
# spurious remove_* operations for them.
_EXTENSION_TABLES = frozenset({"part_config", "part_config_sub"})


def include_object(
    object: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    if type_ == "table" and name in _EXTENSION_TABLES:
        return False
    if type_ == "index" and name is not None and name.startswith("part_config"):
        return False
    schema = getattr(object, "schema", None)
    if schema not in (None, "public"):
        return False
    return True


def get_url() -> str:
    return load_configuration().database.dsn


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
