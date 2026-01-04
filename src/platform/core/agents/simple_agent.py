from __future__ import annotations

from typing import Iterable

from platform.runtime import ChatMessage
from platform.core.agents.base_agent import BaseAgent
from platform.core.streaming.openai_sse import SSEEvent
from platform.core.tools.base_tool import BaseTool
from platform.core.tools.echo import EchoTool


class SimpleAgent(BaseAgent):
    """A tiny agent that echoes the task using the provided toolkit."""

    name = "simple_agent"

    def __init__(self, task: str, toolkit=None, prompts_config=None, **kwargs) -> None:
        super().__init__(task=task, toolkit=toolkit or [EchoTool], prompts_config=prompts_config, **kwargs)

    async def run(self) -> Iterable[SSEEvent]:
        await self._ensure_session_state()
        await self._refresh_prompt_tools()
        system_prompt = self._system_prompt()
        if system_prompt:
            await self._record_message(ChatMessage.text("system", system_prompt))

        user_prompt = self._initial_user_request()
        await self._record_message(ChatMessage.text("user", user_prompt))

        intro = f"Using tools: {', '.join(self.available_tools) or 'none'}"
        message = f"Task: {self.task}"
        response_text = f"{intro}\n{message}"

        await self._record_message(ChatMessage.text("assistant", response_text))
        return self.streaming_generator.stream_text(response_text)
