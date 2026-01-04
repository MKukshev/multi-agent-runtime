from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable, List

import pytest
try:
    from alembic import command
    from alembic.config import Config
except ImportError:  # pragma: no cover - optional dependency guard for CI environments without alembic
    pytest.skip("alembic is required for persistence tests", allow_module_level=True)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform.core.agents.base_agent import BaseAgent, WaitingForClarification
from platform.core.streaming.openai_sse import SSEEvent
from platform.persistence import TemplateRepository
from platform.runtime import ChatMessage, InstancePool, SessionService


def run_migrations(db_path: Path) -> None:
    cfg = Config("src/platform/persistence/migrations/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


class CountingAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.invocations = 0
        self.session_ids: List[str] = []

    async def run(self) -> Iterable[SSEEvent]:
        await self._ensure_session_state()
        self.invocations += 1
        if self.session_context:
            self.session_ids.append(self.session_context.session_id)
        text = f"run-{self.invocations}"
        await self._record_message(ChatMessage.text("assistant", text))
        return self.streaming_generator.stream_text(text)


class ClarificationAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resumed = False

    async def run(self) -> Iterable[SSEEvent]:
        await self._ensure_session_state()
        if not self.resumed:
            self.resumed = True
            await self._record_message(ChatMessage.text("assistant", "need clarification"))
            raise WaitingForClarification("waiting for clarification")
        await self._record_message(ChatMessage.text("assistant", "resumed"))
        return self.streaming_generator.stream_text("resumed")


@pytest.mark.anyio
async def test_instance_pool_reuses_worker_without_recreation(tmp_path: Path) -> None:
    db_path = tmp_path / "pool.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, module=sqlite3)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        template_repo = TemplateRepository(session)
        template = await template_repo.create_template(name="agent", description="demo")
        version = await template_repo.create_version(template.id, settings={"temperature": 0.1}, prompt="Hello")
        await session.commit()

    service = SessionService(session_factory)
    pool = InstancePool(service)

    first_agent = None
    instance_id = None
    for idx in range(5):
        instance = await pool.claim(agent_cls=CountingAgent, task=f"task-{idx}", template_version_id=version.id)
        if first_agent is None:
            first_agent = instance.agent
            instance_id = instance.id
        else:
            assert instance.agent is first_agent
            assert instance.id == instance_id

        events = list(await instance.execute(task=f"task-{idx}"))
        assert events[0].data["choices"][0]["delta"]["content"].endswith(str(idx + 1))

        await pool.release(instance.id)
        assert instance.agent.session_context is None
        assert instance.current_session_id is None

    assert first_agent.invocations == 5
    assert len(first_agent.session_ids) == 5

    await engine.dispose()


@pytest.mark.anyio
async def test_instance_pool_validates_template_version_on_claim(tmp_path: Path) -> None:
    db_path = tmp_path / "pool_version.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, module=sqlite3)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        template_repo = TemplateRepository(session)
        template = await template_repo.create_template(name="agent", description="demo")
        version = await template_repo.create_version(template.id, settings={"temperature": 0.2}, prompt="Hello")
        other_version = await template_repo.create_version(
            template.id, settings={"temperature": 0.3}, prompt="Hi again", version=2
        )
        await session.commit()

    service = SessionService(session_factory)
    pool = InstancePool(service)

    instance = await pool.claim(agent_cls=CountingAgent, task="first", template_version_id=version.id)
    await instance.execute(task="first")
    session_id = instance.agent.session_context.session_id  # type: ignore[assignment]
    await pool.release(instance.id)

    with pytest.raises(ValueError):
        await pool.claim(
            agent_cls=CountingAgent,
            task="mismatch",
            template_version_id=other_version.id,
            session_id=session_id,
        )

    await engine.dispose()


@pytest.mark.anyio
async def test_waiting_session_can_resume_without_blocking(tmp_path: Path) -> None:
    db_path = tmp_path / "waiting.db"
    run_migrations(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, module=sqlite3)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        template_repo = TemplateRepository(session)
        template = await template_repo.create_template(name="agent", description="demo")
        version = await template_repo.create_version(template.id, settings={"temperature": 0.5}, prompt="Wait")
        await session.commit()

    service = SessionService(session_factory)
    agent = ClarificationAgent(task="clarify", session_service=service, template_version_id=version.id)

    initial_events = await agent.execute()
    assert list(initial_events) == []

    context, history = await service.resume_session(agent.session_context.session_id)  # type: ignore[arg-type]
    assert context.state == "WAITING"
    assert history.messages[-1].content[0].text == "need clarification"

    resumed_events = list(await agent.resume(context.session_id))
    assert resumed_events[0].data["choices"][0]["delta"]["content"] == "resumed"

    updated_context, updated_history = await service.resume_session(context.session_id)
    assert updated_context.state == "COMPLETED"
    assert updated_history.messages[-1].content[0].text == "resumed"

    await engine.dispose()
