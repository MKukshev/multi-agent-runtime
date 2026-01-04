from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Type

from platform.retrieval.tool_search import ToolSearchService
from platform.runtime.templates import TemplateRuntimeConfig, TemplateService
from platform.security import RulesEngine

from platform.core.agents.base_agent import BaseAgent
from platform.core.services.registry import AgentRegistry
from platform.core.streaming.openai_sse import SSEEvent
from platform.retrieval.agent_directory import AgentDirectoryEntry, AgentDirectoryService
from platform.runtime.session_service import SessionContext, SessionService


@dataclass(slots=True)
class RouteResult:
    """Outcome of a routing decision and execution."""

    entry: AgentDirectoryEntry | None
    events: Iterable[SSEEvent]
    session_context: SessionContext | None = None


class AgentRouter:
    """Router that picks a template via semantic search and launches a session."""

    def __init__(
        self,
        agent_directory: AgentDirectoryService,
        session_service: SessionService | None = None,
        template_service: TemplateService | None = None,
        tool_search_service: ToolSearchService | None = None,
        rules_engine: RulesEngine | None = None,
        *,
        default_agent_cls: Type[BaseAgent] | None = None,
    ) -> None:
        self._agent_directory = agent_directory
        self._session_service = session_service
        self._template_service = template_service
        self._tool_search_service = tool_search_service
        self._rules_engine = rules_engine or RulesEngine()
        self._default_agent_cls = default_agent_cls

    async def route(
        self,
        task: str,
        *,
        top_k: int | None = None,
        session_id: str | None = None,
        entry: AgentDirectoryEntry | None = None,
    ) -> RouteResult:
        """Search for a suitable template and execute the matching agent."""

        if entry is None:
            results = await self._agent_directory.search(query=task, top_k=top_k)
            entry = results[0] if results else None
        agent_cls = self._resolve_agent(entry)
        template_config = await self._template_config(entry)
        agent = agent_cls(
            task=task,
            session_service=self._session_service if entry else None,
            template_version_id=entry.version.id if entry else None,
            template_config=template_config,
            tool_search_service=self._tool_search_service,
            rules_engine=self._rules_engine,
        )
        events = await agent.execute(session_id=session_id)
        return RouteResult(entry=entry, events=events, session_context=agent.session_context)

    def _resolve_agent(self, entry: AgentDirectoryEntry | None) -> Type[BaseAgent]:
        if entry is None:
            return self._default_agent()
        try:
            return AgentRegistry.get(entry.template.name)
        except KeyError:
            return self._default_agent()

    async def _template_config(self, entry: AgentDirectoryEntry | None) -> TemplateRuntimeConfig | None:
        if entry is None or self._template_service is None:
            return None
        return await self._template_service.get_runtime_config_for_version(entry.version.id)

    def _default_agent(self) -> Type[BaseAgent]:
        if self._default_agent_cls is not None:
            return self._default_agent_cls
        from platform.core.agents.simple_agent import SimpleAgent  # lazy import to avoid cycles

        return SimpleAgent


__all__ = ["AgentRouter", "RouteResult"]
