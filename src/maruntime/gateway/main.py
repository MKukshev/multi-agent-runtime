from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maruntime.gateway.routes import create_gateway_router
from maruntime.observability import MetricsReporter
from maruntime.persistence import create_engine, create_session_factory
from maruntime.retrieval.agent_directory import AgentDirectoryService
from maruntime.retrieval.tool_search import ToolSearchService
from maruntime.runtime import SessionService, TemplateService
from maruntime.security import SecurityPolicy

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

engine = create_engine(DATABASE_URL)
session_factory = create_session_factory(engine)
template_service = TemplateService(session_factory)
session_service = SessionService(session_factory)
agent_directory = AgentDirectoryService(session_factory)
tool_search = ToolSearchService(session_factory)
security_policy = SecurityPolicy()
metrics = MetricsReporter()

app = FastAPI(title="Multi-Agent Gateway", version="0.1.0")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(
    create_gateway_router(
        session_service=session_service,
        template_service=template_service,
        agent_directory=agent_directory,
        tool_search=tool_search,
        session_factory=session_factory,
        security=security_policy,
        metrics=metrics,
    )
)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    await engine.dispose()
