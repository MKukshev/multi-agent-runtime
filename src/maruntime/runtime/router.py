from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Type

from maruntime.retrieval.tool_search import ToolSearchService
from maruntime.runtime.templates import TemplateRuntimeConfig, TemplateService
from maruntime.security import RulesEngine

from maruntime.core.agents.base_agent import BaseAgent
from maruntime.core.services.registry import AgentRegistry, ToolRegistry
from maruntime.core.streaming.openai_sse import SSEEvent
from maruntime.retrieval.agent_directory import AgentDirectoryEntry, AgentDirectoryService
from maruntime.runtime.session_service import SessionContext, SessionService


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
        template_config = await self._template_config(entry)
        agent_cls = self._resolve_agent(entry, template_config)

        # Load toolkit from template config
        toolkit = self._resolve_toolkit(template_config)

        agent = agent_cls(
            task=task,
            toolkit=toolkit,
            session_service=self._session_service if entry else None,
            template_version_id=entry.version.id if entry else None,
            template_config=template_config,
            tool_search_service=self._tool_search_service,
            rules_engine=self._rules_engine,
        )
        events = await agent.execute(session_id=session_id)
        return RouteResult(entry=entry, events=events, session_context=agent.session_context)

    def _resolve_agent(
        self, entry: AgentDirectoryEntry | None, template_config: TemplateRuntimeConfig | None
    ) -> Type[BaseAgent]:
        # Try to load agent class from template_config.base_class
        if template_config and template_config.base_class:
            try:
                return self._import_agent_class(template_config.base_class)
            except Exception as e:
                import logging
                logging.warning(f"Failed to load agent class '{template_config.base_class}': {e}")

        # Fallback to AgentRegistry by template name
        if entry is not None:
            try:
                return AgentRegistry.get(entry.template.name)
            except KeyError:
                pass

        return self._default_agent()

    def _import_agent_class(self, class_path: str) -> Type[BaseAgent]:
        """Import agent class from module:ClassName path."""
        if ":" not in class_path:
            raise ValueError(f"Invalid class path format: {class_path}. Expected 'module:ClassName'")

        module_path, class_name = class_path.rsplit(":", 1)
        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        if not issubclass(cls, BaseAgent):
            raise TypeError(f"{class_path} is not a subclass of BaseAgent")

        return cls

    async def _template_config(self, entry: AgentDirectoryEntry | None) -> TemplateRuntimeConfig | None:
        if entry is None or self._template_service is None:
            return None
        return await self._template_service.get_runtime_config_for_version(entry.version.id)

    def _default_agent(self) -> Type[BaseAgent]:
        if self._default_agent_cls is not None:
            return self._default_agent_cls
        from maruntime.core.agents.simple_agent import SimpleAgent  # lazy import to avoid cycles

        return SimpleAgent

    def _resolve_toolkit(self, template_config: TemplateRuntimeConfig | None) -> list:
        """Resolve tool names from template config to tool classes."""
        if template_config is None or not template_config.tools:
            return []
        try:
            return ToolRegistry.resolve(template_config.tools)
        except KeyError as e:
            # Log warning but continue with available tools
            import logging
            logging.warning(f"Some tools not found in registry: {e}")
            # Try to resolve available tools
            resolved = []
            for tool_name in template_config.tools:
                try:
                    resolved.append(ToolRegistry.get(tool_name))
                except KeyError:
                    pass
            return resolved


__all__ = ["AgentRouter", "RouteResult"]
