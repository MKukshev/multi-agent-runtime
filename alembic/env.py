from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from maruntime.persistence import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    # Convert async URLs to sync for Alembic
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    if url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite+aiosqlite://", "sqlite://")
    return url


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
