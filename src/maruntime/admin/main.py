from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from maruntime.persistence import (
    AgentInstance,
    AgentTemplate,
    Session as SessionModel,
    SystemPrompt,
    TemplateVersion,
    Tool,
    create_engine,
    create_session_factory,
)
from maruntime.persistence.repositories import AgentInstanceRepository, SystemPromptRepository, TemplateRepository, ToolRepository
from maruntime.runtime.templates import ExecutionPolicy, LLMPolicy, PromptConfig, TemplateService, ToolPolicy
from maruntime.core.services.prompt_loader import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_INITIAL_USER_REQUEST,
    DEFAULT_CLARIFICATION_RESPONSE,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

engine: AsyncEngine = create_engine(DATABASE_URL)
session_factory = create_session_factory(engine)
template_service = TemplateService(session_factory)

app = FastAPI(title="Multi-Agent Admin API", version="0.1.0")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ToolCreate(BaseModel):
    name: str
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    category: str = "utility"
    is_active: bool = True


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class ToolRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    category: str = "utility"
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
    instance_id: Optional[str] = None
    instance_name: Optional[str] = None  # Populated from join
    state: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentInstanceRead(BaseModel):
    """Response model for agent instances."""
    id: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    template_id: str
    template_version_id: str
    current_session_id: Optional[str] = None
    status: str
    is_enabled: bool
    auto_start: bool
    priority: int
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    total_sessions: int = 0
    total_messages: int = 0
    total_tool_calls: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentInstanceCreate(BaseModel):
    """Request model for creating an agent instance."""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    template_version_id: str
    is_enabled: bool = True
    auto_start: bool = False
    priority: int = 0
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class AgentInstanceUpdate(BaseModel):
    """Request model for updating an agent instance."""
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    template_version_id: Optional[str] = None
    is_enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    priority: Optional[int] = None
    config_overrides: Optional[dict[str, Any]] = None


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


class TemplateVersionPromptUpdate(BaseModel):
    """Update system prompt for a template version."""
    system_prompt: str


@app.patch(
    "/templates/{template_id}/versions/{version_id}/prompt",
    response_model=TemplateVersionRead,
    dependencies=[Depends(require_api_key)],
)
async def update_template_version_prompt(
    template_id: str,
    version_id: str,
    payload: TemplateVersionPromptUpdate,
    session: AsyncSession = Depends(get_session),
) -> TemplateVersionRead:
    """Update the system prompt of a template version."""
    version = await session.get(TemplateVersion, version_id)
    if version is None or version.template_id != template_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template version not found")
    
    # Update settings.prompts.system_prompt
    settings = dict(version.settings) if version.settings else {}
    if "prompts" not in settings:
        settings["prompts"] = {}
    settings["prompts"]["system_prompt"] = payload.system_prompt
    
    version.settings = settings
    await session.commit()
    await session.refresh(version)
    
    return TemplateVersionRead.model_validate(version)


@app.get("/sessions", response_model=list[SessionRead], dependencies=[Depends(require_api_key)])
async def list_sessions(
    template_version_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    state: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> list[SessionRead]:
    """List sessions with optional filters."""
    stmt = select(SessionModel).options(selectinload(SessionModel.instance))
    if template_version_id:
        stmt = stmt.where(SessionModel.template_version_id == template_version_id)
    if instance_id:
        stmt = stmt.where(SessionModel.instance_id == instance_id)
    if state:
        stmt = stmt.where(SessionModel.state == state)
    stmt = stmt.order_by(SessionModel.created_at.desc())
    result = await session.scalars(stmt)
    sessions = result.all()

    # Build response with instance name
    response = []
    for sess in sessions:
        data = SessionRead.model_validate(sess)
        if sess.instance:
            data.instance_name = sess.instance.name
        response.append(data)
    return response


@app.get("/sessions/{session_id}", response_model=SessionRead, dependencies=[Depends(require_api_key)])
async def get_session_by_id(session_id: str, session: AsyncSession = Depends(get_session)) -> SessionRead:
    """Get a specific session by ID."""
    stmt = select(SessionModel).options(selectinload(SessionModel.instance)).where(SessionModel.id == session_id)
    result = await session.scalars(stmt)
    sess = result.first()
    if sess is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    data = SessionRead.model_validate(sess)
    if sess.instance:
        data.instance_name = sess.instance.name
    return data


@app.get("/instances", response_model=list[AgentInstanceRead], dependencies=[Depends(require_api_key)])
async def list_agent_instances(
    template_id: Optional[str] = None,
    template_version_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    session: AsyncSession = Depends(get_session),
) -> list[AgentInstanceRead]:
    """List all agent instances with optional filters."""
    repo = AgentInstanceRepository(session)
    instances = await repo.list(
        template_id=template_id,
        template_version_id=template_version_id,
        status=status_filter,
        is_enabled=is_enabled,
    )
    return [AgentInstanceRead.model_validate(instance) for instance in instances]


@app.post("/instances", response_model=AgentInstanceRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def create_agent_instance(
    payload: AgentInstanceCreate,
    session: AsyncSession = Depends(get_session),
) -> AgentInstanceRead:
    """Create a new named agent instance."""
    repo = AgentInstanceRepository(session)

    # Check if name is unique
    existing = await repo.get_by_name(payload.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Instance with this name already exists")

    instance = await repo.create(
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        template_version_id=payload.template_version_id,
        is_enabled=payload.is_enabled,
        auto_start=payload.auto_start,
        priority=payload.priority,
        config_overrides=payload.config_overrides,
    )
    await session.commit()
    await session.refresh(instance)
    return AgentInstanceRead.model_validate(instance)


@app.get("/instances/{instance_id}", response_model=AgentInstanceRead, dependencies=[Depends(require_api_key)])
async def get_agent_instance(instance_id: str, session: AsyncSession = Depends(get_session)) -> AgentInstanceRead:
    """Get a specific agent instance by ID."""
    repo = AgentInstanceRepository(session)
    instance = await repo.get(instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return AgentInstanceRead.model_validate(instance)


@app.patch("/instances/{instance_id}", response_model=AgentInstanceRead, dependencies=[Depends(require_api_key)])
async def update_agent_instance(
    instance_id: str,
    payload: AgentInstanceUpdate,
    session: AsyncSession = Depends(get_session),
) -> AgentInstanceRead:
    """Update an agent instance configuration."""
    repo = AgentInstanceRepository(session)

    # Check name uniqueness if being changed
    if payload.name:
        existing = await repo.get_by_name(payload.name)
        if existing and existing.id != instance_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Instance with this name already exists")

    instance = await repo.update(
        instance_id,
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        template_version_id=payload.template_version_id,
        is_enabled=payload.is_enabled,
        auto_start=payload.auto_start,
        priority=payload.priority,
        config_overrides=payload.config_overrides,
    )
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    await session.commit()
    await session.refresh(instance)
    return AgentInstanceRead.model_validate(instance)


@app.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_agent_instance(instance_id: str, session: AsyncSession = Depends(get_session)) -> None:
    """Delete an agent instance."""
    repo = AgentInstanceRepository(session)
    deleted = await repo.delete(instance_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    await session.commit()


@app.post("/instances/{instance_id}/start", response_model=AgentInstanceRead, dependencies=[Depends(require_api_key)])
async def start_agent_instance(instance_id: str, session: AsyncSession = Depends(get_session)) -> AgentInstanceRead:
    """Start an agent instance (set status to IDLE)."""
    repo = AgentInstanceRepository(session)
    instance = await repo.start(instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    await session.commit()
    await session.refresh(instance)
    return AgentInstanceRead.model_validate(instance)


@app.post("/instances/{instance_id}/stop", response_model=AgentInstanceRead, dependencies=[Depends(require_api_key)])
async def stop_agent_instance(instance_id: str, session: AsyncSession = Depends(get_session)) -> AgentInstanceRead:
    """Stop an agent instance (set status to OFFLINE)."""
    repo = AgentInstanceRepository(session)
    instance = await repo.stop(instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    await session.commit()
    await session.refresh(instance)
    return AgentInstanceRead.model_validate(instance)


# ============================================================================
# System Prompts
# ============================================================================

class SystemPromptRead(BaseModel):
    """Response model for system prompts."""
    id: str
    name: str
    description: Optional[str] = None
    content: str
    placeholders: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SystemPromptUpdate(BaseModel):
    """Request model for updating system prompts."""
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    placeholders: Optional[list[str]] = None
    is_active: Optional[bool] = None


class SystemPromptDefaultsResponse(BaseModel):
    """Response containing default prompts for reset."""
    system: str
    initial_user: str
    clarification: str


# Mapping of prompt IDs to their defaults
_PROMPT_DEFAULTS = {
    "system": DEFAULT_SYSTEM_PROMPT,
    "initial_user": DEFAULT_INITIAL_USER_REQUEST,
    "clarification": DEFAULT_CLARIFICATION_RESPONSE,
}


@app.get("/prompts", response_model=list[SystemPromptRead], dependencies=[Depends(require_api_key)])
async def list_system_prompts(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[SystemPromptRead]:
    """List all system prompts."""
    repo = SystemPromptRepository(session)
    prompts = await repo.list(active_only=active_only)
    return [SystemPromptRead.model_validate(prompt) for prompt in prompts]


@app.get("/prompts/defaults", response_model=SystemPromptDefaultsResponse, dependencies=[Depends(require_api_key)])
async def get_prompt_defaults() -> SystemPromptDefaultsResponse:
    """Get the hardcoded default prompts for reference or reset."""
    return SystemPromptDefaultsResponse(
        system=DEFAULT_SYSTEM_PROMPT,
        initial_user=DEFAULT_INITIAL_USER_REQUEST,
        clarification=DEFAULT_CLARIFICATION_RESPONSE,
    )


@app.get("/prompts/{prompt_id}", response_model=SystemPromptRead, dependencies=[Depends(require_api_key)])
async def get_system_prompt(prompt_id: str, session: AsyncSession = Depends(get_session)) -> SystemPromptRead:
    """Get a specific system prompt by ID."""
    repo = SystemPromptRepository(session)
    prompt = await repo.get(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System prompt not found")
    return SystemPromptRead.model_validate(prompt)


@app.patch("/prompts/{prompt_id}", response_model=SystemPromptRead, dependencies=[Depends(require_api_key)])
async def update_system_prompt(
    prompt_id: str,
    payload: SystemPromptUpdate,
    session: AsyncSession = Depends(get_session),
) -> SystemPromptRead:
    """Update a system prompt."""
    repo = SystemPromptRepository(session)
    prompt = await repo.update(
        prompt_id,
        name=payload.name,
        description=payload.description,
        content=payload.content,
        placeholders=payload.placeholders,
        is_active=payload.is_active,
    )
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System prompt not found")
    await session.commit()
    await session.refresh(prompt)
    return SystemPromptRead.model_validate(prompt)


@app.post("/prompts/{prompt_id}/reset", response_model=SystemPromptRead, dependencies=[Depends(require_api_key)])
async def reset_system_prompt(prompt_id: str, session: AsyncSession = Depends(get_session)) -> SystemPromptRead:
    """Reset a system prompt to its default content."""
    default_content = _PROMPT_DEFAULTS.get(prompt_id)
    if default_content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No default available for prompt ID: {prompt_id}"
        )

    repo = SystemPromptRepository(session)
    prompt = await repo.reset_to_default(prompt_id, default_content)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System prompt not found")
    await session.commit()
    await session.refresh(prompt)
    return SystemPromptRead.model_validate(prompt)
