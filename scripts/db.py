from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config

from platform.persistence import Base, create_engine

DEFAULT_DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
ROOT_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(url: str, config_path: Optional[str] = None) -> Config:
    ini_path = Path(config_path) if config_path else ROOT_DIR / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


async def init_database(url: str, *, stamp: bool = True, config_path: Optional[str] = None) -> None:
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    if stamp:
        cfg = _alembic_config(url, config_path)
        command.stamp(cfg, "head")


def upgrade_database(url: str, revision: str = "head", *, config_path: Optional[str] = None) -> None:
    cfg = _alembic_config(url, config_path)
    command.upgrade(cfg, revision)


def downgrade_database(url: str, revision: str = "-1", *, config_path: Optional[str] = None) -> None:
    cfg = _alembic_config(url, config_path)
    command.downgrade(cfg, revision)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Database management CLI for the runtime catalog.")
    parser.add_argument("--url", default=DEFAULT_DB_URL, help="Database URL (overrides DATABASE_URL).")
    parser.add_argument(
        "--alembic-config",
        default=None,
        help="Optional path to alembic.ini (defaults to repository-level config).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create database schema using SQLAlchemy metadata.")
    init_parser.add_argument(
        "--no-stamp",
        action="store_true",
        help="Do not stamp the database with the latest Alembic revision after initialization.",
    )

    upgrade_parser = subparsers.add_parser("upgrade", help="Apply Alembic migrations.")
    upgrade_parser.add_argument("revision", nargs="?", default="head", help="Target revision (default: head).")

    downgrade_parser = subparsers.add_parser("downgrade", help="Revert Alembic migrations.")
    downgrade_parser.add_argument("revision", nargs="?", default="-1", help="Target revision (default: -1).")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    url = args.url
    config_path = args.alembic_config

    if args.command == "init":
        asyncio.run(init_database(url, stamp=not args.no_stamp, config_path=config_path))
    elif args.command == "upgrade":
        upgrade_database(url, args.revision, config_path=config_path)
    elif args.command == "downgrade":
        downgrade_database(url, args.revision, config_path=config_path)


if __name__ == "__main__":
    main()
