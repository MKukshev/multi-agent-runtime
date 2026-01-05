from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT = PROJECT_ROOT / "alembic"


async def run_migrations(db_path: Path) -> None:
    """Apply Alembic migrations from the repository-level configuration."""

    pytest.importorskip("alembic")
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    loop = asyncio.get_event_loop()
    if loop.is_running():
        await loop.run_in_executor(None, command.upgrade, cfg, "head")
    else:
        command.upgrade(cfg, "head")
