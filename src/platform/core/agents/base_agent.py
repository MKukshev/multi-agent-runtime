from __future__ import annotations

import abc
import uuid
from typing import Any, ClassVar, Iterable, List, Sequence, Type

from platform.core.services.prompt_loader import PromptsConfig, PromptLoader
from platform.core.services.registry import AgentRegistry
from platform.core.streaming.openai_sse import OpenAIStreamingGenerator, SSEEvent
from platform.core.tools.base_tool import BaseTool
from platform.retrieval.tool_search import ToolSearchService
from platform.runtime.session_service import ChatMessage, MessageStore, SessionContext, SessionService
from platform.runtime.templates import TemplateRuntimeConfig, ToolPolicy
from platform.security import RulePhase, RulesEngine


class AgentRegistryMixin:
    """Mixin that auto-registers agent classes in the global registry."""

    agent_registry: ClassVar[AgentRegistry] = AgentRegistry

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401
        """Register every subclass except the abstract base class."""
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "BaseAgent":
            cls.agent_registry.register(cls)


class WaitingForClarification(RuntimeError):
    """Signal that the agent requires external clarification before continuing."""


class BaseAgent(AgentRegistryMixin, abc.ABC):
    """Minimal async agent skeleton with SSE streaming support."""

    name: ClassVar[str] = "base_agent"

    def __init__(
        self,
        task: str,
        toolkit: Iterable[Type[BaseTool]] | None = None,
        prompts_config: PromptsConfig | None = None,
        *,
        session_service: SessionService | None = None,
        session_context: SessionContext | None = None,
        message_store: MessageStore | None = None,
        template_version_id: str | None = None,
        context_data: dict[str, Any] | None = None,
        tool_policy: ToolPolicy | dict[str, Any] | None = None,
        tool_search_service: ToolSearchService | None = None,
        template_config: TemplateRuntimeConfig | None = None,
        rules_engine: RulesEngine | None = None,
    ) -> None:
        self.id = f"{self.name}_{uuid.uuid4()}"
        self.task = task
        self.toolkit: List[Type[BaseTool]] = list(toolkit or [])
        self.prompts_config = prompts_config or PromptsConfig()
        self.streaming_generator = OpenAIStreamingGenerator(model=self.id)
        self.session_service = session_service
        self.session_context = session_context
        self.message_store = message_store
        self.template_version_id = template_version_id
        self.tool_policy = tool_policy if isinstance(tool_policy, ToolPolicy) else ToolPolicy(**(tool_policy or {}))
        self.tool_search_service = tool_search_service
        self.template_config = template_config
        self.rules_engine = rules_engine or RulesEngine()
        self._prompt_tool_names: list[str] | None = None
        self._context_data: dict[str, Any] = (
            dict(context_data) if context_data is not None else dict(getattr(session_context, "data", {}) or {})
        )
        self._stage: str | None = None

    @property
    def available_tools(self) -> Sequence[str]:
        return [tool.tool_name or tool.__name__.lower() for tool in self.toolkit]

    @abc.abstractmethod
    async def run(self) -> Iterable[SSEEvent]:
        """Execute the agent workflow and yield SSE events."""

    @property
    def prompt_tool_names(self) -> list[str]:
        return list(self._prompt_tool_names or self.available_tools)

    def _system_prompt(self) -> str:
        return PromptLoader.get_system_prompt(self.prompt_tool_names, self.prompts_config)

    def _initial_user_request(self) -> str:
        return PromptLoader.get_initial_user_request(self.task, self.prompts_config)

    async def _refresh_prompt_tools(self) -> list[str]:
        if self._prompt_tool_names is not None:
            return self._prompt_tool_names

        policy = self.tool_policy or ToolPolicy()
        available = self.available_tools
        pre_rule_decision = None
        if self.rules_engine:
            pre_rule_decision = self.rules_engine.evaluate(
                self.session_context, self.template_config, phase=RulePhase.PRE_RETRIEVAL
            )
            available = pre_rule_decision.apply(available)

        if self.tool_search_service:
            session_id = self.session_context.session_id if self.session_context else self.id
            search_result = await self.tool_search_service.search(
                session_id=session_id,
                query=self.task,
                policy=policy,
                available_tools=available,
                required_tools=policy.required_tools,
                top_k=policy.max_tools_in_prompt,
            )
            names = [tool.name for tool in search_result.tools]
        else:
            names = self._apply_policy_filters(available, policy)

        if policy.max_tools_in_prompt:
            names = names[: policy.max_tools_in_prompt]

        if self.rules_engine:
            post_rule_decision = self.rules_engine.evaluate(
                self.session_context, self.template_config, phase=RulePhase.POST_RETRIEVAL
            )
            names = post_rule_decision.apply(names)
            self._stage = (
                post_rule_decision.stage
                or (pre_rule_decision.stage if pre_rule_decision else None)
                or self._stage
            )

        self._prompt_tool_names = names
        return names

    @staticmethod
    def _apply_policy_filters(available: Sequence[str], policy: ToolPolicy) -> list[str]:
        required = list(dict.fromkeys(policy.required_tools or []))
        allowlist = set(policy.allowlist or [])
        denylist = set(policy.denylist or [])

        filtered: list[str] = []
        for name in available:
            if allowlist and name not in allowlist and name not in required:
                continue
            if name in denylist:
                continue
            filtered.append(name)
        ordered: list[str] = []
        for name in required:
            if name in filtered:
                ordered.append(name)
        ordered.extend([name for name in filtered if name not in required])
        return ordered

    async def _ensure_session_state(self) -> None:
        if self.session_service:
            if self.session_context:
                self.session_context, self.message_store = await self.session_service.resume_session(
                    self.session_context.session_id
                )
                self._context_data = dict(self.session_context.data)
            elif self.template_version_id:
                self.session_context, self.message_store = await self.session_service.start_session(
                    self.template_version_id, context=self._context_data
                )
            else:
                msg = "template_version_id is required to start a session"
                raise ValueError(msg)

        if self.message_store is None:
            self.message_store = MessageStore(session_id=self.session_context.session_id if self.session_context else self.id)

        if self.session_context is None:
            self.session_context = SessionContext(
                session_id=self.message_store.session_id,
                template_version_id=self.template_version_id or "ephemeral",
                data=self._context_data,
            )

    async def _persist_context(self) -> None:
        self.session_context.data = dict(self._context_data)
        if self.session_service:
            self.session_context = await self.session_service.update_context(
                self.session_context.session_id, self._context_data
            )

    async def _record_message(self, message: ChatMessage) -> ChatMessage:
        await self._ensure_session_state()
        self.message_store.append(message)
        self._context_data["history_length"] = len(self.message_store.messages)
        self._context_data["last_role"] = message.role
        if self.session_service:
            await self.session_service.save_message(self.session_context.session_id, message)
        await self._persist_context()
        return message

    def reset(self) -> None:
        """Clear session-scoped state so the agent can handle a new session."""

        self.session_context = None
        self.message_store = None
        self._context_data = {}
        self._prompt_tool_names = None

    async def execute(self, *, session_id: str | None = None) -> Iterable[SSEEvent]:
        """Run the agent workflow with persistence-aware state handling."""

        if session_id:
            if not self.session_service:
                msg = "session_service is required to resume a session"
                raise ValueError(msg)
            self.session_context, self.message_store = await self.session_service.resume_session(session_id)
            self._context_data = dict(self.session_context.data)

        await self._ensure_session_state()
        if self.session_service:
            await self.session_service.set_state(self.session_context.session_id, "ACTIVE")

        try:
            events = await self.run()
            if self.session_service:
                await self.session_service.set_state(self.session_context.session_id, "COMPLETED")
            return events
        except WaitingForClarification:
            if self.session_service:
                await self.session_service.set_state(self.session_context.session_id, "WAITING")
            return []
        except Exception:
            if self.session_service and self.session_context:
                await self.session_service.set_state(self.session_context.session_id, "FAILED")
            raise

    async def resume(self, session_id: str) -> Iterable[SSEEvent]:
        """Resume execution for an existing session."""

        return await self.execute(session_id=session_id)
