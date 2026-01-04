from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Iterable, Type

from platform.runtime.session_service import SessionContext, SessionService

if TYPE_CHECKING:
    from platform.core.agents.base_agent import BaseAgent


class AgentInstance:
    """Long-lived worker bound to a specific template version."""

    def __init__(
        self,
        agent_cls: Type["BaseAgent"],
        template_version_id: str,
        *,
        session_service: SessionService | None = None,
        agent_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.agent_cls = agent_cls
        self.template_version_id = template_version_id
        self.session_service = session_service
        self._agent_kwargs = dict(agent_kwargs or {})
        self._agent = agent_cls(
            session_service=session_service, template_version_id=template_version_id, **self._agent_kwargs
        )
        self.current_session_id: str | None = None

    @property
    def busy(self) -> bool:
        return self.current_session_id is not None

    @property
    def agent(self) -> "BaseAgent":
        return self._agent

    async def claim(
        self, *, session_id: str | None = None, context: SessionContext | None = None
    ) -> SessionContext | None:
        if self.busy:
            msg = f"AgentInstance {self.id} is already handling session {self.current_session_id}"
            raise RuntimeError(msg)

        context: SessionContext | None = None
        if context:
            if session_id and context.session_id != session_id:
                msg = f"Provided context belongs to session {context.session_id}, expected {session_id}"
                raise ValueError(msg)
            if context.template_version_id != self.template_version_id:
                msg = (
                    f"Session {context.session_id} belongs to template version {context.template_version_id}, "
                    f"expected {self.template_version_id}"
                )
                raise ValueError(msg)
        elif session_id and self.session_service:
            context, _ = await self.session_service.resume_session(session_id)
            if context.template_version_id != self.template_version_id:
                msg = f"Session {session_id} belongs to template version {context.template_version_id}, expected {self.template_version_id}"
                raise ValueError(msg)

        target_session_id = session_id or (context.session_id if context else None)
        self.current_session_id = target_session_id or "__NEW__"
        return context

    async def execute(
        self, *, task: str, session_id: str | None = None, context_data: dict[str, Any] | None = None
    ) -> Iterable:
        if not self.busy:
            await self.claim(session_id=session_id)
        elif session_id and self.current_session_id != session_id:
            msg = f"AgentInstance {self.id} is already claimed for session {self.current_session_id}"
            raise RuntimeError(msg)

        if context_data is not None:
            self.agent._context_data = dict(context_data)
        self.agent.task = task
        events = await self.agent.execute(session_id=session_id)
        if self.agent.session_context:
            self.current_session_id = self.agent.session_context.session_id
        return events

    async def reset(self) -> None:
        self.agent.reset()
        self.current_session_id = None

    async def release(self) -> None:
        await self.reset()


class InstancePool:
    """In-memory pool of agent instances keyed by template version."""

    def __init__(self, session_service: SessionService | None = None):
        self.session_service = session_service
        self._instances_by_template: dict[str, list[AgentInstance]] = {}
        self._instances_by_id: dict[str, AgentInstance] = {}

    async def _resolve_template_version(
        self, *, template_version_id: str | None, session_id: str | None
    ) -> tuple[str, SessionContext | None]:
        if session_id:
            if not self.session_service:
                msg = "session_service is required to resolve template version from session_id"
                raise ValueError(msg)
            context, _ = await self.session_service.resume_session(session_id)
            if template_version_id and template_version_id != context.template_version_id:
                msg = (
                    f"Session {session_id} bound to template version {context.template_version_id}, "
                    f"but {template_version_id} was requested"
                )
                raise ValueError(msg)
            return context.template_version_id, context

        if not template_version_id:
            msg = "template_version_id is required when session_id is not provided"
            raise ValueError(msg)
        return template_version_id, None

    def _pick_idle(self, template_version_id: str, agent_cls: Type["BaseAgent"]) -> AgentInstance | None:
        for instance in self._instances_by_template.get(template_version_id, []):
            if not instance.busy and instance.agent_cls is agent_cls:
                return instance
        return None

    async def claim(
        self,
        *,
        agent_cls: Type["BaseAgent"],
        task: str,
        template_version_id: str | None = None,
        session_id: str | None = None,
        context_data: dict[str, Any] | None = None,
        agent_kwargs: dict[str, Any] | None = None,
    ) -> AgentInstance:
        resolved_template_version, context = await self._resolve_template_version(
            template_version_id=template_version_id, session_id=session_id
        )

        instance = self._pick_idle(resolved_template_version, agent_cls)
        if instance is None:
            instance = AgentInstance(
                agent_cls,
                resolved_template_version,
                session_service=self.session_service,
                agent_kwargs={"task": task, **(agent_kwargs or {})},
            )
            self._instances_by_template.setdefault(resolved_template_version, []).append(instance)
            self._instances_by_id[instance.id] = instance

        await instance.claim(session_id=session_id, context=context)
        if context_data is not None:
            instance.agent._context_data = dict(context_data)
        instance.agent.task = task
        return instance

    async def release(self, instance_id: str) -> AgentInstance:
        if instance_id not in self._instances_by_id:
            msg = f"Unknown instance id {instance_id}"
            raise KeyError(msg)
        instance = self._instances_by_id[instance_id]
        await instance.release()
        return instance

    async def reset(self, instance_id: str) -> AgentInstance:
        if instance_id not in self._instances_by_id:
            msg = f"Unknown instance id {instance_id}"
            raise KeyError(msg)
        instance = self._instances_by_id[instance_id]
        await instance.reset()
        return instance
