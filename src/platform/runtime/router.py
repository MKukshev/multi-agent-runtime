from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Type

from platform.core.agents.base_agent import BaseAgent
from platform.core.services.registry import AgentRegistry
from platform.core.streaming.openai_sse import SSEEvent
from platform.retrieval.agent_directory import AgentDirectoryEntry, AgentDirectoryService
from platform.runtime.session_service import SessionService


@dataclass(slots=True)
class RouteResult:
    """Outcome of a routing decision and execution."""

    entry: AgentDirectoryEntry | None
    events: Iterable[SSEEvent]


class AgentRouter:
    """Router that picks a template via semantic search and launches a session."""

    def __init__(
        self,
        agent_directory: AgentDirectoryService,
        session_service: SessionService | None = None,
        *,
        default_agent_cls: Type[BaseAgent] | None = None,
    ) -> None:
        self._agent_directory = agent_directory
        self._session_service = session_service
        self._default_agent_cls = default_agent_cls

    async def route(self, task: str, *, top_k: int | None = None) -> RouteResult:
        """Search for a suitable template and execute the matching agent."""

        results = await self._agent_directory.search(query=task, top_k=top_k)
        entry = results[0] if results else None
        agent_cls = self._resolve_agent(entry)
        agent = agent_cls(
            task=task,
            session_service=self._session_service if entry else None,
            template_version_id=entry.version.id if entry else None,
        )
        events = await agent.execute()
        return RouteResult(entry=entry, events=events)

    def _resolve_agent(self, entry: AgentDirectoryEntry | None) -> Type[BaseAgent]:
        if entry is None:
            return self._default_agent()
        try:
            return AgentRegistry.get(entry.template.name)
        except KeyError:
            return self._default_agent()

    def _default_agent(self) -> Type[BaseAgent]:
        if self._default_agent_cls is not None:
            return self._default_agent_cls
        from platform.core.agents.simple_agent import SimpleAgent  # lazy import to avoid cycles

        return SimpleAgent


__all__ = ["AgentRouter", "RouteResult"]
