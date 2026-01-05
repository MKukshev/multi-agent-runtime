"""Repository layer for database operations."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import (
    AgentInstance,
    AgentTemplate,
    Artifact,
    Session,
    SessionMessage,
    Source,
    SystemPrompt,
    TemplateVersion,
    Tool,
    ToolExecution,
)


def create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class ToolRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        description: Optional[str] = None,
        python_entrypoint: Optional[str] = None,
        config: Optional[dict] = None,
        embedding: Optional[Iterable[float]] = None,
        is_active: bool = True,
    ) -> Tool:
        tool = Tool(
            name=name,
            description=description,
            python_entrypoint=python_entrypoint,
            config=config or {},
            embedding=list(embedding) if embedding is not None else None,
            is_active=is_active,
        )
        self.session.add(tool)
        await self.session.flush()
        return tool

    async def get(self, tool_id: str) -> Optional[Tool]:
        return await self.session.get(Tool, tool_id)

    async def list(self, active_only: bool | None = None) -> Sequence[Tool]:
        stmt = select(Tool)
        if active_only is True:
            stmt = stmt.where(Tool.is_active.is_(True))
        elif active_only is False:
            stmt = stmt.where(Tool.is_active.is_(False))
        result = await self.session.scalars(stmt.order_by(Tool.created_at))
        return result.all()

    async def update(
        self,
        tool_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        python_entrypoint: Optional[str] = None,
        config: Optional[dict] = None,
        embedding: Optional[Iterable[float]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Tool]:
        tool = await self.get(tool_id)
        if tool is None:
            return None
        if name is not None:
            tool.name = name
        if description is not None:
            tool.description = description
        if python_entrypoint is not None:
            tool.python_entrypoint = python_entrypoint
        if config is not None:
            tool.config = config
        if embedding is not None:
            tool.embedding = list(embedding)
        if is_active is not None:
            tool.is_active = is_active
        await self.session.flush()
        return tool

    async def set_active(self, tool_id: str, active: bool = True) -> Optional[Tool]:
        return await self.update(tool_id, is_active=active)


class TemplateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_template(self, name: str, description: Optional[str] = None) -> AgentTemplate:
        template = AgentTemplate(name=name, description=description)
        self.session.add(template)
        await self.session.flush()
        return template

    async def get_template(self, template_id: str) -> Optional[AgentTemplate]:
        return await self.session.get(AgentTemplate, template_id)

    async def list_templates(self) -> Sequence[AgentTemplate]:
        result = await self.session.scalars(select(AgentTemplate).order_by(AgentTemplate.created_at))
        return result.all()

    async def _next_version(self, template_id: str) -> int:
        result = await self.session.execute(
            select(TemplateVersion.version).where(TemplateVersion.template_id == template_id).order_by(
                TemplateVersion.version.desc()
            )
        )
        current = result.scalars().first()
        return 1 if current is None else current + 1

    async def create_version(
        self,
        template_id: str,
        *,
        version: Optional[int] = None,
        settings: Optional[dict] = None,
        embedding: Optional[Iterable[float]] = None,
        prompt: Optional[str] = None,
        tools: Optional[list] = None,
        is_active: bool = False,
    ) -> TemplateVersion:
        version_number = version or await self._next_version(template_id)
        template_version = TemplateVersion(
            template_id=template_id,
            version=version_number,
            settings=settings or {},
            embedding=list(embedding) if embedding is not None else None,
            prompt=prompt,
            tools=tools or [],
            is_active=is_active,
        )
        self.session.add(template_version)
        await self.session.flush()
        if is_active:
            await self.activate_version(template_id, template_version.id)
        return template_version

    async def list_versions(self, template_id: str) -> Sequence[TemplateVersion]:
        result = await self.session.scalars(
            select(TemplateVersion).where(TemplateVersion.template_id == template_id).order_by(TemplateVersion.version)
        )
        return result.all()

    async def activate_version(self, template_id: str, version_id: str) -> Optional[TemplateVersion]:
        template = await self.get_template(template_id)
        if template is None:
            return None

        # Deactivate others
        result = await self.session.scalars(
            select(TemplateVersion).where(TemplateVersion.template_id == template_id)
        )
        for tv in result:
            tv.is_active = tv.id == version_id

        template.active_version_id = version_id
        await self.session.flush()
        return await self.session.get(TemplateVersion, version_id)


class SessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self,
        template_version_id: str,
        *,
        state: str = "ACTIVE",
        context: Optional[dict] = None,
    ) -> Session:
        session_obj = Session(template_version_id=template_version_id, state=state, context=context or {})
        self.session.add(session_obj)
        await self.session.flush()
        return session_obj

    async def get_session(self, session_id: str) -> Optional[Session]:
        return await self.session.get(Session, session_id)

    async def update_context(self, session_id: str, context: dict) -> Optional[Session]:
        session_obj = await self.get_session(session_id)
        if session_obj is None:
            return None
        session_obj.context = context
        session_obj.updated_at = datetime.utcnow()
        await self.session.flush()
        return session_obj

    async def update_state(self, session_id: str, state: str) -> Optional[Session]:
        session_obj = await self.get_session(session_id)
        if session_obj is None:
            return None
        session_obj.state = state
        session_obj.updated_at = datetime.utcnow()
        await self.session.flush()
        return session_obj

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: dict,
        *,
        tool_call_id: Optional[str] = None,
    ) -> SessionMessage:
        message = SessionMessage(session_id=session_id, role=role, content=content, tool_call_id=tool_call_id)
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(self, session_id: str) -> Sequence[SessionMessage]:
        result = await self.session.scalars(
            select(SessionMessage).where(SessionMessage.session_id == session_id).order_by(SessionMessage.created_at)
        )
        return result.all()

    async def set_instance(self, session_id: str, instance_id: str) -> Optional[Session]:
        """Link a session to an agent instance."""
        session_obj = await self.get_session(session_id)
        if session_obj is None:
            return None
        session_obj.instance_id = instance_id
        session_obj.updated_at = datetime.utcnow()
        await self.session.flush()
        return session_obj

    async def log_tool_execution(
        self,
        session_id: str,
        tool_name: str,
        *,
        tool_id: Optional[str] = None,
        arguments: Optional[dict] = None,
        result: Optional[dict] = None,
        status: str = "PENDING",
    ) -> ToolExecution:
        execution = ToolExecution(
            session_id=session_id,
            tool_id=tool_id,
            tool_name=tool_name,
            arguments=arguments or {},
            result=result,
            status=status,
        )
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def list_tool_executions(self, session_id: str) -> Sequence[ToolExecution]:
        result = await self.session.scalars(
            select(ToolExecution).where(ToolExecution.session_id == session_id).order_by(ToolExecution.created_at)
        )
        return result.all()

    async def add_source(self, session_id: str, uri: str, metadata: Optional[dict] = None) -> Source:
        source = Source(session_id=session_id, uri=uri, metadata_json=metadata or {})
        self.session.add(source)
        await self.session.flush()
        return source

    async def add_artifact(
        self,
        name: str,
        type: str,  # noqa: A003 - align with column name
        payload: dict,
        *,
        session_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Artifact:
        artifact = Artifact(name=name, type=type, payload=payload, session_id=session_id, source_id=source_id)
        self.session.add(artifact)
        await self.session.flush()
        return artifact


class AgentInstanceRepository:
    """Repository for managing named agent instances (slots)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        template_version_id: str,
        *,
        template_id: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        is_enabled: bool = True,
        auto_start: bool = False,
        priority: int = 0,
        config_overrides: dict | None = None,
    ) -> AgentInstance:
        """Create a new named agent instance."""
        template_identifier = template_id
        if template_identifier is None:
            template_version = await self.session.get(TemplateVersion, template_version_id)
            if template_version is None:
                msg = f"TemplateVersion {template_version_id} not found"
                raise ValueError(msg)
            template_identifier = template_version.template_id

        instance = AgentInstance(
            name=name,
            display_name=display_name,
            description=description,
            template_id=template_identifier,
            template_version_id=template_version_id,
            status="OFFLINE",
            is_enabled=is_enabled,
            auto_start=auto_start,
            priority=priority,
            config_overrides=config_overrides or {},
        )
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get(self, instance_id: str) -> Optional[AgentInstance]:
        """Get instance by ID."""
        result = await self.session.scalars(select(AgentInstance).where(AgentInstance.id == instance_id))
        return result.first()

    async def get_by_name(self, name: str) -> Optional[AgentInstance]:
        """Get instance by unique name."""
        result = await self.session.scalars(select(AgentInstance).where(AgentInstance.name == name))
        return result.first()

    async def list(
        self,
        *,
        template_id: str | None = None,
        template_version_id: str | None = None,
        status: str | None = None,
        is_enabled: bool | None = None,
        auto_start: bool | None = None,
    ) -> Sequence[AgentInstance]:
        """List instances with optional filters."""
        stmt = select(AgentInstance)
        if template_id:
            stmt = stmt.where(AgentInstance.template_id == template_id)
        if template_version_id:
            stmt = stmt.where(AgentInstance.template_version_id == template_version_id)
        if status:
            stmt = stmt.where(AgentInstance.status == status)
        if is_enabled is not None:
            stmt = stmt.where(AgentInstance.is_enabled == is_enabled)
        if auto_start is not None:
            stmt = stmt.where(AgentInstance.auto_start == auto_start)
        result = await self.session.scalars(stmt.order_by(AgentInstance.priority.desc(), AgentInstance.name))
        return result.all()

    async def update(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        template_version_id: str | None = None,
        is_enabled: bool | None = None,
        auto_start: bool | None = None,
        priority: int | None = None,
        config_overrides: dict | None = None,
    ) -> Optional[AgentInstance]:
        """Update instance configuration."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        if name is not None:
            instance.name = name
        if display_name is not None:
            instance.display_name = display_name
        if description is not None:
            instance.description = description
        if template_version_id is not None:
            instance.template_version_id = template_version_id
        if is_enabled is not None:
            instance.is_enabled = is_enabled
        if auto_start is not None:
            instance.auto_start = auto_start
        if priority is not None:
            instance.priority = priority
        if config_overrides is not None:
            instance.config_overrides = config_overrides
        await self.session.flush()
        return instance

    async def delete(self, instance_id: str) -> bool:
        """Delete an instance. Returns True if deleted."""
        instance = await self.get(instance_id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def start(self, instance_id: str) -> Optional[AgentInstance]:
        """Start an instance (set status to STARTING -> IDLE)."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        if instance.status not in ("OFFLINE", "ERROR"):
            return instance  # Already running or stopping
        instance.status = "IDLE"
        instance.started_at = datetime.utcnow()
        instance.stopped_at = None
        instance.last_heartbeat = datetime.utcnow()
        await self.session.flush()
        return instance

    async def stop(self, instance_id: str) -> Optional[AgentInstance]:
        """Stop an instance (set status to OFFLINE)."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        instance.status = "OFFLINE"
        instance.stopped_at = datetime.utcnow()
        instance.current_session_id = None
        await self.session.flush()
        return instance

    async def claim_session(self, instance_id: str, session_id: str) -> Optional[AgentInstance]:
        """Assign a session to the instance (set status to BUSY)."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        if instance.status != "IDLE":
            return None  # Can only claim if IDLE
        instance.current_session_id = session_id
        instance.status = "BUSY"
        instance.total_sessions += 1
        await self.session.flush()
        return instance

    async def release_session(self, instance_id: str) -> Optional[AgentInstance]:
        """Release current session (set status back to IDLE)."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        instance.current_session_id = None
        instance.status = "IDLE"
        await self.session.flush()
        return instance

    async def heartbeat(self, instance_id: str) -> Optional[AgentInstance]:
        """Update heartbeat timestamp."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        instance.last_heartbeat = datetime.utcnow()
        await self.session.flush()
        return instance

    async def record_error(self, instance_id: str, error_message: str) -> Optional[AgentInstance]:
        """Record an error on the instance."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        instance.error_count += 1
        instance.last_error = error_message
        instance.last_error_at = datetime.utcnow()
        instance.status = "ERROR"
        await self.session.flush()
        return instance

    async def increment_stats(
        self,
        instance_id: str,
        *,
        messages: int = 0,
        tool_calls: int = 0,
    ) -> Optional[AgentInstance]:
        """Increment session statistics."""
        instance = await self.get(instance_id)
        if instance is None:
            return None
        if messages:
            instance.total_messages += messages
        if tool_calls:
            instance.total_tool_calls += tool_calls
        await self.session.flush()
        return instance

    async def get_auto_start_instances(self) -> Sequence[AgentInstance]:
        """Get all enabled instances with auto_start=True."""
        stmt = (
            select(AgentInstance)
            .where(AgentInstance.is_enabled.is_(True))
            .where(AgentInstance.auto_start.is_(True))
            .order_by(AgentInstance.priority.desc(), AgentInstance.name)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def get_idle_instance_for_template(self, template_id: str) -> Optional[AgentInstance]:
        """Get first available (IDLE) instance for a template."""
        stmt = (
            select(AgentInstance)
            .where(AgentInstance.template_id == template_id)
            .where(AgentInstance.is_enabled.is_(True))
            .where(AgentInstance.status == "IDLE")
            .order_by(AgentInstance.priority.desc(), AgentInstance.name)
            .limit(1)
        )
        result = await self.session.scalars(stmt)
        return result.first()


class SystemPromptRepository:
    """Repository for managing system-wide prompt templates."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, prompt_id: str) -> Optional[SystemPrompt]:
        """Get a system prompt by ID."""
        return await self.session.get(SystemPrompt, prompt_id)

    async def list(self, active_only: bool = True) -> Sequence[SystemPrompt]:
        """List all system prompts."""
        stmt = select(SystemPrompt)
        if active_only:
            stmt = stmt.where(SystemPrompt.is_active.is_(True))
        result = await self.session.scalars(stmt.order_by(SystemPrompt.id))
        return result.all()

    async def get_all_as_dict(self, active_only: bool = True) -> dict[str, str]:
        """Get all prompts as a dictionary {id: content}."""
        prompts = await self.list(active_only=active_only)
        return {p.id: p.content for p in prompts}

    async def update(
        self,
        prompt_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        placeholders: Optional[list[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[SystemPrompt]:
        """Update a system prompt."""
        prompt = await self.get(prompt_id)
        if prompt is None:
            return None
        if name is not None:
            prompt.name = name
        if description is not None:
            prompt.description = description
        if content is not None:
            prompt.content = content
        if placeholders is not None:
            prompt.placeholders = placeholders
        if is_active is not None:
            prompt.is_active = is_active
        prompt.updated_at = datetime.utcnow()
        await self.session.flush()
        return prompt

    async def create(
        self,
        prompt_id: str,
        name: str,
        content: str,
        *,
        description: Optional[str] = None,
        placeholders: Optional[list[str]] = None,
        is_active: bool = True,
    ) -> SystemPrompt:
        """Create a new system prompt."""
        prompt = SystemPrompt(
            id=prompt_id,
            name=name,
            description=description,
            content=content,
            placeholders=placeholders or [],
            is_active=is_active,
        )
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def reset_to_default(self, prompt_id: str, default_content: str) -> Optional[SystemPrompt]:
        """Reset a prompt to its default content."""
        return await self.update(prompt_id, content=default_content)
