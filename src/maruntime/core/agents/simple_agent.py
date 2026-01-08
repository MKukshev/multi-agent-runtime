from __future__ import annotations

from typing import AsyncGenerator

from maruntime.runtime import ChatMessage
from maruntime.core.agents.base_agent import BaseAgent
from maruntime.core.streaming.openai_sse import SSEEvent
from maruntime.core.tools.base_tool import BaseTool
from maruntime.core.tools.echo import EchoTool


class SimpleAgent(BaseAgent):
    """A tiny agent that echoes the task using the provided toolkit."""

    name = "simple_agent"

    def __init__(self, task: str, toolkit=None, prompts_config=None, **kwargs) -> None:
        super().__init__(task=task, toolkit=toolkit or [EchoTool], prompts_config=prompts_config, **kwargs)

    async def run(self) -> AsyncGenerator[SSEEvent, None]:
        await self._ensure_session_state()
        await self._refresh_prompt_tools()
        system_prompt = self._system_prompt()
        if system_prompt:
            await self._record_message(ChatMessage.text("system", system_prompt))

        user_prompt = self._initial_user_request()  # Formatted for LLM (not used in simple agent)
        # Save original task to DB (without formatting)
        await self._record_message(ChatMessage.text("user", self.task))

        intro = f"Using tools: {', '.join(self.available_tools) or 'none'}"
        message = f"Task: {self.task}"
        response_text = f"{intro}\n{message}"

        await self._record_message(ChatMessage.text("assistant", response_text))
        for event in self.streaming_generator.stream_text(response_text):
            yield event
