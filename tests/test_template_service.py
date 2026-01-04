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
from platform.runtime import (
    ExecutionPolicy,
    LLMPolicy,
    PromptConfig,
    TemplateRuntimeConfig,
    TemplateService,
    ToolPolicy,
)


def run_migrations(db_path: Path) -> None:
    cfg = Config("src/platform/persistence/migrations/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_template_service_create_and_activate(tmp_path: Path) -> None:
    db_path = tmp_path / "templates.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, module=sqlite3)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    service = TemplateService(session_factory)

    template = await service.create(name="analyst", description="Research analyst agent")

    llm_policy = LLMPolicy(model="gpt-4o", base_url="https://api.openai.com", temperature=0.1, max_tokens=512)
    prompts = PromptConfig(system="system prompt", initial_user="Hello", clarification="Clarify please")
    execution_policy = ExecutionPolicy(max_iterations=8, max_clarifications=2, max_searches=3, time_budget_seconds=120)
    tool_policy = ToolPolicy(
        required_tools=["search"],
        allowlist=["search", "browse"],
        denylist=["forbidden"],
        max_tools_in_prompt=2,
        selection_strategy="static",
    )

    version_one = await service.create_version(
        template.id,
        llm_policy=llm_policy,
        prompts=prompts,
        execution_policy=execution_policy,
        tool_policy=tool_policy,
        tools=["search"],
        prompt="system prompt",
        activate=True,
    )

    active_config = await service.get_active(template.id)
    assert isinstance(active_config, TemplateRuntimeConfig)
    assert active_config.version_id == version_one.id
    assert active_config.llm_policy.model == "gpt-4o"
    assert active_config.prompts.initial_user == "Hello"
    assert active_config.execution_policy.max_iterations == 8
    assert active_config.tool_policy.required_tools == ["search"]
    assert active_config.tools == ["search"]

    updated_policy = LLMPolicy(model="gpt-4o-mini", temperature=0.6)
    version_two = await service.create_version(
        template.id,
        llm_policy=updated_policy,
        prompts=prompts,
        execution_policy=execution_policy,
        tool_policy=tool_policy,
        tools=["browse"],
        prompt="updated prompt",
    )

    activated_config = await service.activate(template.id, version_two.id)
    assert activated_config is not None
    assert activated_config.version_id == version_two.id
    assert activated_config.llm_policy.model == "gpt-4o-mini"
    assert activated_config.tools == ["browse"]
    assert activated_config.prompt == "updated prompt"

    async with session_factory() as session:
        repo = TemplateRepository(session)
        versions = await repo.list_versions(template.id)
        assert {v.id: v.is_active for v in versions} == {
            version_one.id: False,
            version_two.id: True,
        }

    await engine.dispose()
