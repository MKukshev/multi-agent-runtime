import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform.core.streaming.openai_sse import SSEEvent
from platform.persistence import Base, Session
from platform.retrieval.agent_directory import AgentDirectoryService
from platform.runtime import (
    ExecutionPolicy,
    LLMPolicy,
    PromptConfig,
    SessionService,
    TemplateService,
    ToolPolicy,
)
from platform.runtime.router import AgentRouter


async def _session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True, module=sqlite3)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_template(
    service: TemplateService, name: str, description: str, embedding_text: str
) -> None:
    template = await service.create(name=name, description=description)
    await service.create_version(
        template.id,
        llm_policy=LLMPolicy(model="demo"),
        prompts=PromptConfig(system=f"{name} prompt"),
        execution_policy=ExecutionPolicy(),
        tool_policy=ToolPolicy(),
        tools=[],
        prompt=f"{name} prompt",
        activate=True,
        embedding_text=embedding_text,
    )


@pytest.mark.anyio
async def test_agent_directory_search_and_route() -> None:
    factory = await _session_factory()
    template_service = TemplateService(factory)
    await _create_template(
        template_service,
        "analyst",
        "Performs research and analysis",
        embedding_text="research analysis data insights reports",
    )
    await _create_template(
        template_service,
        "writer",
        "Drafts narratives and summaries",
        embedding_text="write summary",
    )

    session_service = SessionService(factory)
    directory = AgentDirectoryService(factory)
    router = AgentRouter(directory, session_service=session_service)

    result = await router.route("write summary")
    events = list(result.events)

    assert result.entry is not None
    assert result.entry.template.name == "writer"
    assert any(isinstance(event, SSEEvent) for event in events)

    async with factory() as session:
        recorded_sessions = list((await session.scalars(select(Session))).all())
    assert len(recorded_sessions) == 1
