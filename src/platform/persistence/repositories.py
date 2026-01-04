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
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_instance(self, template_version_id: str, status: str = "IDLE") -> AgentInstance:
        instance = AgentInstance(template_version_id=template_version_id, status=status)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get_instance(self, instance_id: str) -> Optional[AgentInstance]:
        return await self.session.get(AgentInstance, instance_id)

    async def claim_instance(self, instance_id: str, session_id: str, status: str = "BUSY") -> Optional[AgentInstance]:
        instance = await self.get_instance(instance_id)
        if instance is None:
            return None
        instance.session_id = session_id
        instance.status = status
        await self.session.flush()
        return instance

    async def release_instance(self, instance_id: str) -> Optional[AgentInstance]:
        instance = await self.get_instance(instance_id)
        if instance is None:
            return None
        instance.session_id = None
        instance.status = "IDLE"
        await self.session.flush()
        return instance

    async def heartbeat(self, instance_id: str) -> Optional[AgentInstance]:
        instance = await self.get_instance(instance_id)
        if instance is None:
            return None
        instance.last_heartbeat = datetime.utcnow()
        await self.session.flush()
        return instance
