from __future__ import annotations

import logging
import sqlite3
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from maruntime.core.agents.base_agent import BaseAgent, WaitingForClarification
from maruntime.observability import MetricsReporter, get_logger
from maruntime.persistence import Base
from maruntime.persistence.repositories import SessionRepository, ToolRepository
from maruntime.retrieval.agent_directory import AgentDirectoryService
from maruntime.retrieval.tool_search import ToolSearchService
from maruntime.runtime import ExecutionPolicy, LLMPolicy, PromptConfig, SessionService, TemplateService, ToolPolicy
from maruntime.gateway.routes import create_gateway_router
from maruntime.security import AllowlistPolicy, RiskPolicy, SecurityPolicy


class WaitingAgent(BaseAgent):
    name = "waiter"

    async def run(self) -> list[Any]:
        await self._ensure_session_state()
        raise WaitingForClarification()


async def _make_services() -> tuple[FastAPI, TemplateService, SessionService, AgentDirectoryService, ToolSearchService, MetricsReporter, async_sessionmaker, AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True, module=sqlite3)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    template_service = TemplateService(session_factory)
    session_service = SessionService(session_factory)
    directory = AgentDirectoryService(session_factory)
    tool_search = ToolSearchService(session_factory)
    metrics = MetricsReporter()
    security = SecurityPolicy(
        allowlist=AllowlistPolicy(models={"writer", "waiter", "retriever", "delegate"}),
        risk=RiskPolicy(banned_terms=["forbidden"]),
    )
    logger = get_logger("gateway-test")
    logger.setLevel(logging.INFO)

    app = FastAPI()
    app.include_router(
        create_gateway_router(
            session_service,
            template_service,
            directory,
            tool_search,
            security=security,
            metrics=metrics,
            logger=logger,
        )
    )
    return app, template_service, session_service, directory, tool_search, metrics, session_factory, engine


async def _create_template(
    template_service: TemplateService,
    name: str,
    *,
    tools: list[str] | None = None,
    tool_policy: ToolPolicy | None = None,
    embedding_text: str,
) -> str:
    template = await template_service.create(name=name, description=name)
    version = await template_service.create_version(
        template.id,
        llm_policy=LLMPolicy(model=name),
        prompts=PromptConfig(system=f"{name} system prompt"),
        execution_policy=ExecutionPolicy(),
        tool_policy=tool_policy or ToolPolicy(),
        tools=tools or [],
        prompt=f"{name} prompt",
        activate=True,
        embedding_text=embedding_text,
    )
    return version.id


def _client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_chat_completions_streams_and_tracks_metrics() -> None:
    app, template_service, _, _, _, metrics, _, engine = await _make_services()
    await _create_template(template_service, "writer", embedding_text="write stories")

    payload = {
        "model": "writer",
        "messages": [{"role": "user", "content": "hello world"}],
        "stream": True,
    }
    async with _client(app) as client:
        response = await client.post("/v1/chat/completions", json=payload)
        text = ""
        async for chunk in response.aiter_text():
            text += chunk

    assert response.status_code == 200
    assert "event: message" in text
    assert "x-session-id" in response.headers
    snapshot = metrics.snapshot()
    assert snapshot["chat.completions.status.success"] == 1
    await engine.dispose()


@pytest.mark.anyio
async def test_waiting_state_and_resume_flow() -> None:
    app, template_service, session_service, _, _, _, session_factory, engine = await _make_services()
    await _create_template(template_service, "waiter", embedding_text="wait for user")

    payload = {"model": "waiter", "messages": [{"role": "user", "content": "need pause"}], "stream": False}
    async with _client(app) as client:
        first_response = await client.post("/v1/chat/completions", json=payload)
    session_id = first_response.headers.get("x-session-id")
    assert session_id is not None

    async with session_factory() as db:
        repo = SessionRepository(db)
        session_obj = await repo.get_session(session_id)
    assert session_obj is not None
    assert session_obj.state == "WAITING"

    resume_payload = {"model": session_id, "messages": [{"role": "user", "content": "resume"}], "stream": False}
    async with _client(app) as client:
        resumed = await client.post("/v1/chat/completions", json=resume_payload)
    assert resumed.status_code == 200
    assert resumed.headers.get("x-session-id") == session_id
    await engine.dispose()


@pytest.mark.anyio
async def test_retrieval_tool_allowlist_and_history_persistence() -> None:
    app, template_service, session_service, _, tool_search, _, session_factory, engine = await _make_services()
    tool_policy = ToolPolicy(allowlist=["echo"], required_tools=["echo"])
    await _create_template(template_service, "retriever", tools=["echo"], tool_policy=tool_policy, embedding_text="retrieve info")

    async with session_factory() as db:
        repo = ToolRepository(db)
        await repo.create(name="echo", description="echo tool", embedding=[0.1, 0.2, 0.3])
        await db.commit()

    payload = {
        "model": "retriever",
        "messages": [{"role": "user", "content": "fetch something"}],
        "stream": False,
    }
    async with _client(app) as client:
        response = await client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    session_id = response.headers.get("x-session-id")
    assert session_id
    context, history = await session_service.resume_session(session_id)
    assert context.data.get("history_length") == len(history.messages)
    assert any("Using tools" in item.content[0].text for item in history.messages if item.role == "assistant")
    await engine.dispose()


@pytest.mark.anyio
async def test_delegation_route_selects_best_template() -> None:
    app, template_service, session_service, _, _, _, _, engine = await _make_services()
    target_version = await _create_template(template_service, "delegate", embedding_text="delegate-choice")
    other_version = await _create_template(template_service, "writer", embedding_text="write stories")
    assert target_version != other_version

    payload = {
        "model": "delegate",
        "messages": [{"role": "user", "content": "delegate-choice"}],
        "stream": False,
    }
    async with _client(app) as client:
        response = await client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    session_id = response.headers.get("x-session-id")
    assert session_id
    context, _ = await session_service.resume_session(session_id)
    assert context.template_version_id == target_version
    await engine.dispose()


@pytest.mark.anyio
async def test_risk_policy_rejects_forbidden_prompt() -> None:
    app, template_service, *_, engine = await _make_services()
    await _create_template(template_service, "writer", embedding_text="write stories")

    payload = {"model": "writer", "messages": [{"role": "user", "content": "this is forbidden content"}], "stream": False}
    async with _client(app) as client:
        response = await client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 403
    await engine.dispose()
