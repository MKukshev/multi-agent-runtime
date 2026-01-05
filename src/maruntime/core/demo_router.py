from __future__ import annotations

import asyncio
import sqlite3
from typing import Iterable

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from maruntime.core.streaming.openai_sse import SSEEvent
from maruntime.persistence import Base
from maruntime.retrieval.agent_directory import AgentDirectoryEntry, AgentDirectoryService
from maruntime.runtime import (
    ExecutionPolicy,
    LLMPolicy,
    PromptConfig,
    SessionService,
    TemplateService,
    ToolPolicy,
)
from maruntime.runtime.router import AgentRouter


async def _prepare_database() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True, module=sqlite3)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_template_version(
    service: TemplateService, name: str, description: str, *, embedding_text: str
) -> None:
    template = await service.create(name=name, description=description)
    llm_policy = LLMPolicy(model="demo-model")
    prompts = PromptConfig(system=f"{name} system prompt")
    execution = ExecutionPolicy(max_iterations=4)
    tool_policy = ToolPolicy()
    await service.create_version(
        template.id,
        llm_policy=llm_policy,
        prompts=prompts,
        execution_policy=execution,
        tool_policy=tool_policy,
        tools=[],
        prompt=prompts.system,
        activate=True,
        embedding_text=embedding_text,
    )


async def run_router_demo(task: str) -> tuple[AgentDirectoryEntry | None, Iterable[SSEEvent]]:
    """Demonstrate routing between multiple templates."""

    session_factory = await _prepare_database()
    template_service = TemplateService(session_factory)
    await _create_template_version(
        template_service,
        "analyst",
        "Performs research and analysis",
        embedding_text="research analysis data insights reports",
    )
    await _create_template_version(
        template_service,
        "writer",
        "Drafts narratives and summaries",
        embedding_text="writing summaries storytelling content drafting",
    )

    session_service = SessionService(session_factory)
    directory = AgentDirectoryService(session_factory)
    router = AgentRouter(directory, session_service=session_service)

    result = await router.route(task)
    return result.entry, result.events


def main() -> None:
    entry, events = asyncio.run(run_router_demo("Write a short summary about data trends"))
    chosen = entry.template.name if entry else "default"
    print(f"Selected template: {chosen}")
    for event in events:
        print(event.render(), end="")


if __name__ == "__main__":  # pragma: no cover - manual execution entrypoint
    main()
