from pathlib import Path
import sqlite3

import pytest
try:
    from alembic import command
    from alembic.config import Config
except ImportError:  # pragma: no cover - optional dependency guard for CI environments without alembic
    pytest.skip("alembic is required for persistence tests", allow_module_level=True)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform.persistence import TemplateRepository
from platform.runtime import ChatMessage, SessionService


def run_migrations(db_path: Path) -> None:
    cfg = Config("src/platform/persistence/migrations/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_session_service_persists_history(tmp_path: Path) -> None:
    db_path = tmp_path / "session.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, module=sqlite3)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        template_repo = TemplateRepository(session)
        template = await template_repo.create_template(name="agent", description="demo")
        version = await template_repo.create_version(template.id, settings={"temperature": 0.3}, prompt="Hi")
        await session.commit()

    service = SessionService(session_factory)
    context, history = await service.start_session(version.id, context={"iteration": 0})
    assert context.data["iteration"] == 0
    assert history.to_openai() == []

    user_message = ChatMessage.text("user", "hello world")
    await service.save_message(context.session_id, user_message)
    updated_context = await service.update_context(context.session_id, {"iteration": 1})
    assert updated_context.data["iteration"] == 1

    resumed_context, resumed_history = await service.resume_session(context.session_id)
    assert resumed_context.session_id == context.session_id
    assert resumed_context.template_version_id == version.id

    history_payload = resumed_history.to_openai()
    assert len(history_payload) == 1
    assert history_payload[0]["role"] == "user"
    assert history_payload[0]["content"][0]["text"] == "hello world"

    await engine.dispose()
