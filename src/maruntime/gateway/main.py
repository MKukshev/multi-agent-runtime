from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import tools to register them in ToolRegistry
import maruntime.core.tools  # noqa: F401

from maruntime.auth.middleware import AuthMiddleware
from maruntime.auth.routes import create_auth_router
from maruntime.core.services.chat_memory_service import get_chat_memory_service
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

chat_fts_config = os.getenv("CHAT_FTS_CONFIG", "russian")
get_chat_memory_service(session_factory=session_factory, fts_config=chat_fts_config)

app = FastAPI(title="Multi-Agent Gateway", version="0.1.0")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware - validates session cookies and adds user to request.state
app.add_middleware(
    AuthMiddleware,
    session_factory=session_factory,
)

# Auth routes (register, login, logout, etc.)
app.include_router(create_auth_router(session_factory))

# Gateway routes (chat completions, models)
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
