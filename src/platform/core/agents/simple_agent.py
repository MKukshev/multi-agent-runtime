from __future__ import annotations

from typing import Iterable

from platform.core.agents.base_agent import BaseAgent
from platform.core.streaming.openai_sse import SSEEvent
from platform.core.tools.base_tool import BaseTool
from platform.core.tools.echo import EchoTool


class SimpleAgent(BaseAgent):
    """A tiny agent that echoes the task using the provided toolkit."""

    name = "simple_agent"

    def __init__(self, task: str, toolkit=None, prompts_config=None) -> None:
        super().__init__(task=task, toolkit=toolkit or [EchoTool], prompts_config=prompts_config)

    async def run(self) -> Iterable[SSEEvent]:
        intro = f"Using tools: {', '.join(self.available_tools) or 'none'}"
        message = f"Task: {self.task}"
        return self.streaming_generator.stream_text(f"{intro}\n{message}")
