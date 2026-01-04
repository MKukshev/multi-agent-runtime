from __future__ import annotations

import abc
import uuid
from typing import Any, ClassVar, Iterable, List, Sequence, Type

from platform.runtime import ChatMessage, MessageStore, SessionContext, SessionService
from platform.core.services.prompt_loader import PromptsConfig, PromptLoader
from platform.core.services.registry import AgentRegistry
from platform.core.streaming.openai_sse import OpenAIStreamingGenerator, SSEEvent
from platform.core.tools.base_tool import BaseTool


class AgentRegistryMixin:
    """Mixin that auto-registers agent classes in the global registry."""

    agent_registry: ClassVar[AgentRegistry] = AgentRegistry

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401
        """Register every subclass except the abstract base class."""
        super().__init_subclass__(**kwargs)
        if cls is not BaseAgent:
            cls.agent_registry.register(cls)


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
        self._context_data: dict[str, Any] = (
            dict(context_data) if context_data is not None else dict(getattr(session_context, "data", {}) or {})
        )

    @property
    def available_tools(self) -> Sequence[str]:
        return [tool.tool_name or tool.__name__.lower() for tool in self.toolkit]

    @abc.abstractmethod
    async def run(self) -> Iterable[SSEEvent]:
        """Execute the agent workflow and yield SSE events."""

    def _system_prompt(self) -> str:
        return PromptLoader.get_system_prompt(self.available_tools, self.prompts_config)

    def _initial_user_request(self) -> str:
        return PromptLoader.get_initial_user_request(self.task, self.prompts_config)

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
