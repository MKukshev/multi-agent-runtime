from __future__ import annotations

import abc
import uuid
from typing import Any, ClassVar, Iterable, List, Sequence, Type

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
        if cls.__name__ != "BaseAgent":
            cls.agent_registry.register(cls)


class BaseAgent(AgentRegistryMixin, abc.ABC):
    """Minimal async agent skeleton with SSE streaming support."""

    name: ClassVar[str] = "base_agent"

    def __init__(
        self,
        task: str,
        toolkit: Iterable[Type[BaseTool]] | None = None,
        prompts_config: PromptsConfig | None = None,
    ) -> None:
        self.id = f"{self.name}_{uuid.uuid4()}"
        self.task = task
        self.toolkit: List[Type[BaseTool]] = list(toolkit or [])
        self.prompts_config = prompts_config or PromptsConfig()
        self.streaming_generator = OpenAIStreamingGenerator(model=self.id)

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
