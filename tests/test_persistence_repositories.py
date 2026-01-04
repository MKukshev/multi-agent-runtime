from pathlib import Path
import sqlite3

import pytest
try:
    from alembic import command
    from alembic.config import Config
except ImportError:  # pragma: no cover - optional dependency guard for CI environments without alembic
    pytest.skip("alembic is required for persistence tests", allow_module_level=True)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform.persistence import (
    AgentInstanceRepository,
    SessionRepository,
    TemplateRepository,
    ToolRepository,
)


def run_migrations(db_path: Path) -> None:
    cfg = Config("src/platform/persistence/migrations/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_create_and_read_entities(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, module=sqlite3)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        tool_repo = ToolRepository(session)
        template_repo = TemplateRepository(session)
        session_repo = SessionRepository(session)
        instance_repo = AgentInstanceRepository(session)

        tool = await tool_repo.create(
            name="search",
            description="Search tool",
            python_entrypoint="tools.search",
            config={"timeout": 5},
            embedding=[0.1, 0.2, 0.3],
        )

        template = await template_repo.create_template(name="researcher", description="Base template")
        version = await template_repo.create_version(
            template.id,
            settings={"temperature": 0.2},
            prompt="You are a helpful agent.",
            tools=[tool.id],
            is_active=True,
        )

        session_obj = await session_repo.create_session(template_version_id=version.id, context={"iteration": 1})
        await session_repo.add_message(session_obj.id, role="user", content={"text": "Hello"})
        await session_repo.update_state(session_obj.id, "WAITING")
        await session_repo.log_tool_execution(
            session_obj.id,
            tool_name=tool.name,
            tool_id=tool.id,
            arguments={"query": "test"},
            result={"output": "ok"},
            status="SUCCESS",
        )

        source = await session_repo.add_source(session_obj.id, uri="https://example.com", metadata={"kind": "web"})
        artifact = await session_repo.add_artifact(
            "report", "text/plain", {"content": "hi"}, session_id=session_obj.id, source_id=source.id
        )

        instance = await instance_repo.create_instance(template_version_id=version.id)
        await instance_repo.claim_instance(instance.id, session_obj.id, status="BUSY")
        await instance_repo.heartbeat(instance.id)
        await session.commit()

        tools = await tool_repo.list()
        assert tools[0].id == tool.id
        templates = await template_repo.list_templates()
        assert templates[0].active_version_id == version.id

        versions = await template_repo.list_versions(template.id)
        assert versions[0].is_active is True

        messages = await session_repo.list_messages(session_obj.id)
        assert messages[0].content["text"] == "Hello"

        executions = await session_repo.list_tool_executions(session_obj.id)
        assert executions[0].status == "SUCCESS"
        assert artifact.session_id == session_obj.id

        loaded_instance = await instance_repo.get_instance(instance.id)
        assert loaded_instance.session_id == session_obj.id
        assert loaded_instance.template_id == template.id

    await engine.dispose()
