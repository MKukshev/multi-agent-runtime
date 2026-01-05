from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from platform.persistence import (
    AgentInstance,
    AgentTemplate,
    Session as SessionModel,
    TemplateVersion,
    Tool,
    create_engine,
    create_session_factory,
)
from platform.persistence.repositories import AgentInstanceRepository, TemplateRepository, ToolRepository
from platform.runtime.templates import ExecutionPolicy, LLMPolicy, PromptConfig, TemplateService, ToolPolicy

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

engine: AsyncEngine = create_engine(DATABASE_URL)
session_factory = create_session_factory(engine)
template_service = TemplateService(session_factory)

app = FastAPI(title="Multi-Agent Admin API", version="0.1.0")


class ToolCreate(BaseModel):
    name: str
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class ToolRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TemplateVersionCreate(BaseModel):
    llm_policy: LLMPolicy | dict[str, Any]
    prompts: PromptConfig | dict[str, Any] | None = None
    execution_policy: ExecutionPolicy | dict[str, Any] | None = None
    tool_policy: ToolPolicy | dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    rules: list[dict[str, Any]] = Field(default_factory=list)
    version: Optional[int] = None
    activate: bool = False


class TemplateVersionRead(BaseModel):
    id: str
    template_id: str
    version: int
    settings: dict[str, Any] = Field(default_factory=dict)
    prompt: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TemplateRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    active_version_id: Optional[str] = None
    versions: list[TemplateVersionRead] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SessionRead(BaseModel):
    id: str
    template_version_id: str
    state: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentInstanceRead(BaseModel):
    id: str
    template_id: str
    template_version_id: str
    session_id: Optional[str] = None
    status: str
    last_heartbeat: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if ADMIN_API_KEY and x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


async def get_session() -> AsyncSession:
    async with session_factory() as session:
        yield session


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    await engine.dispose()


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools", response_model=list[ToolRead], dependencies=[Depends(require_api_key)])
async def list_tools(active_only: Optional[bool] = None, session: AsyncSession = Depends(get_session)) -> list[ToolRead]:
    repo = ToolRepository(session)
    tools = await repo.list(active_only=active_only)
    return [ToolRead.model_validate(tool) for tool in tools]


@app.post("/tools", response_model=ToolRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def create_tool(payload: ToolCreate, session: AsyncSession = Depends(get_session)) -> ToolRead:
    existing = await session.scalar(select(Tool).where(Tool.name == payload.name))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tool with this name already exists")

    repo = ToolRepository(session)
    tool = await repo.create(
        name=payload.name,
        description=payload.description,
        python_entrypoint=payload.python_entrypoint,
        config=payload.config,
        is_active=payload.is_active,
    )
    await session.commit()
    await session.refresh(tool)
    return ToolRead.model_validate(tool)


@app.get("/tools/{tool_id}", response_model=ToolRead, dependencies=[Depends(require_api_key)])
async def get_tool(tool_id: str, session: AsyncSession = Depends(get_session)) -> ToolRead:
    repo = ToolRepository(session)
    tool = await repo.get(tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return ToolRead.model_validate(tool)


@app.patch("/tools/{tool_id}", response_model=ToolRead, dependencies=[Depends(require_api_key)])
async def update_tool(tool_id: str, payload: ToolUpdate, session: AsyncSession = Depends(get_session)) -> ToolRead:
    repo = ToolRepository(session)
    tool = await repo.update(
        tool_id,
        name=payload.name,
        description=payload.description,
        python_entrypoint=payload.python_entrypoint,
        config=payload.config,
        is_active=payload.is_active,
    )
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    await session.commit()
    await session.refresh(tool)
    return ToolRead.model_validate(tool)


async def _load_template(session: AsyncSession, template_id: str) -> AgentTemplate | None:
    stmt = (
        select(AgentTemplate)
        .options(selectinload(AgentTemplate.versions))
        .where(AgentTemplate.id == template_id)
    )
    result = await session.scalars(stmt)
    template = result.first()
    if template:
        template.versions.sort(key=lambda v: v.version)
    return template


@app.post("/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def create_template(payload: TemplateCreate, session: AsyncSession = Depends(get_session)) -> TemplateRead:
    existing = await session.scalar(select(AgentTemplate).where(AgentTemplate.name == payload.name))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Template with this name already exists")
    repo = TemplateRepository(session)
    template = await repo.create_template(name=payload.name, description=payload.description)
    await session.commit()
    await session.refresh(template)
    return TemplateRead.model_validate(template)


@app.get("/templates", response_model=list[TemplateRead], dependencies=[Depends(require_api_key)])
async def list_templates(session: AsyncSession = Depends(get_session)) -> list[TemplateRead]:
    stmt = select(AgentTemplate).options(selectinload(AgentTemplate.versions)).order_by(AgentTemplate.created_at)
    result = await session.scalars(stmt)
    templates = result.all()
    for template in templates:
        template.versions.sort(key=lambda v: v.version)
    return [TemplateRead.model_validate(template) for template in templates]


@app.get("/templates/{template_id}", response_model=TemplateRead, dependencies=[Depends(require_api_key)])
async def get_template(template_id: str, session: AsyncSession = Depends(get_session)) -> TemplateRead:
    template = await _load_template(session, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateRead.model_validate(template)


@app.post(
    "/templates/{template_id}/versions",
    response_model=TemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def create_template_version(template_id: str, payload: TemplateVersionCreate) -> TemplateVersionRead:
    async with session_factory() as session:
        repo = TemplateRepository(session)
        template = await repo.get_template(template_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    version = await template_service.create_version(
        template_id,
        llm_policy=payload.llm_policy,
        prompts=payload.prompts,
        execution_policy=payload.execution_policy,
        tool_policy=payload.tool_policy,
        tools=payload.tools,
        prompt=payload.prompt,
        version=payload.version,
        activate=payload.activate,
        rules=payload.rules,
    )
    version_with_template = await template_service.get_version_with_template(version.id)
    return TemplateVersionRead.model_validate(version_with_template)


@app.get(
    "/templates/{template_id}/versions",
    response_model=list[TemplateVersionRead],
    dependencies=[Depends(require_api_key)],
)
async def list_template_versions(template_id: str, session: AsyncSession = Depends(get_session)) -> list[TemplateVersionRead]:
    stmt = select(TemplateVersion).where(TemplateVersion.template_id == template_id).order_by(TemplateVersion.version)
    result = await session.scalars(stmt)
    versions = result.all()
    return [TemplateVersionRead.model_validate(version) for version in versions]


@app.post(
    "/templates/{template_id}/versions/{version_id}/activate",
    response_model=TemplateVersionRead,
    dependencies=[Depends(require_api_key)],
)
async def activate_template_version(template_id: str, version_id: str) -> TemplateVersionRead:
    version = await template_service.activate(template_id, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template or version not found")
    refreshed = await template_service.get_version_with_template(version_id)
    return TemplateVersionRead.model_validate(refreshed)


@app.get("/sessions", response_model=list[SessionRead], dependencies=[Depends(require_api_key)])
async def list_sessions(
    template_version_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> list[SessionRead]:
    stmt = select(SessionModel)
    if template_version_id:
        stmt = stmt.where(SessionModel.template_version_id == template_version_id)
    stmt = stmt.order_by(SessionModel.created_at)
    result = await session.scalars(stmt)
    sessions = result.all()
    return [SessionRead.model_validate(sess) for sess in sessions]


@app.get("/instances", response_model=list[AgentInstanceRead], dependencies=[Depends(require_api_key)])
async def list_agent_instances(
    template_id: Optional[str] = None,
    template_version_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> list[AgentInstanceRead]:
    repo = AgentInstanceRepository(session)
    instances = await repo.list_instances(template_id=template_id, template_version_id=template_version_id, status=status_filter)
    return [AgentInstanceRead.model_validate(instance) for instance in instances]
