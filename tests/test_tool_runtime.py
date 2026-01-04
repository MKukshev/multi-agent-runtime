import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform.core.tools.echo import EchoTool
from platform.persistence.models import Base
from platform.persistence.repositories import SessionRepository, TemplateRepository, ToolRepository
from platform.retrieval import ToolDescriptor, ToolExecutor, ToolLoader, ToolSchemaBuilder

try:
    import aiosqlite  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency guard for environments without aiosqlite
    pytest.skip("aiosqlite is required for retrieval tests", allow_module_level=True)


def run_migrations(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()


def test_tool_loader_and_schema_builder() -> None:
    descriptor = ToolDescriptor(
        tool_id="tool-1",
        name="echo",
        description="Echo values",
        python_entrypoint="platform.core.tools.echo:EchoTool",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    tool_cls = ToolLoader.resolve_tool(descriptor)
    assert issubclass(tool_cls, EchoTool)
    instance = ToolLoader.instantiate(descriptor)
    assert isinstance(instance, EchoTool)

    builder = ToolSchemaBuilder([descriptor])
    openai_tools = builder.build_openai_tools()
    assert openai_tools[0]["function"]["name"] == "echo"
    assert openai_tools[0]["function"]["parameters"]["properties"]["text"]["type"] == "string"

    StructuredModel = builder.build_sgr_schema()
    parsed = StructuredModel.model_validate({"function": {"name": "echo", "arguments": {"text": "hi"}}})
    assert parsed.function.name == "echo"
    assert parsed.function.arguments["text"] == "hi"


def test_tool_executor_logs_execution(tmp_path: Path) -> None:
    asyncio.run(_test_tool_executor_logs_execution(tmp_path))


async def _test_tool_executor_logs_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "test_tool_executor.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        tool_repo = ToolRepository(session)
        template_repo = TemplateRepository(session)
        session_repo = SessionRepository(session)

        tool_record = await tool_repo.create(
            name="echo",
            description="Echo tool",
            python_entrypoint="platform.core.tools.echo:EchoTool",
            config={"input_schema": {"type": "object", "properties": {"payload": {"type": "string"}}}},
        )
        template = await template_repo.create_template("runner")
        version = await template_repo.create_version(template.id, tools=[tool_record.id], is_active=True)
        session_obj = await session_repo.create_session(template_version_id=version.id)

        executor = ToolExecutor(session_repo)
        result = await executor.execute(EchoTool(), session_obj.id, tool_id=tool_record.id, arguments={"payload": "hello"})
        assert result["echo"]["payload"] == "hello"

        await session.commit()
        executions = await session_repo.list_tool_executions(session_obj.id)
        assert executions[0].status == "SUCCESS"
        assert executions[0].result["echo"]["payload"] == "hello"

    await engine.dispose()
