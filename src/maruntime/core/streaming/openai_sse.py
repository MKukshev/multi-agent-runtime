from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Generator, Iterable


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """Represents a single SSE event."""

    event: str
    data: dict

    def render(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {payload}\n\n"


class OpenAIStreamingGenerator:
    """Simplified OpenAI-compatible SSE generator with agent step support."""

    def __init__(self, model: str) -> None:
        self.model = model
        self._step_start_time: float | None = None

    def stream_text(self, text: str, chunk_size: int = 32) -> Iterable[SSEEvent]:
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]
        for chunk in chunks:
            yield SSEEvent(
                event="message",
                data={"id": self.model, "object": "chat.completion.chunk", "model": self.model, "choices": [{"delta": {"content": chunk}}]},
            )
        yield SSEEvent(
            event="done",
            data={"id": self.model, "object": "chat.completion.chunk", "model": self.model, "choices": [{"delta": {"content": ""}}], "finish_reason": "stop"},
        )

    # === Agent Step Events ===

    def step_start(self, step: int, max_steps: int, description: str = "") -> SSEEvent:
        """Emit event when a new agent step starts."""
        self._step_start_time = time.time()
        return SSEEvent(
            event="step_start",
            data={
                "step": step,
                "max_steps": max_steps,
                "description": description,
                "status": "running",
                "timestamp": int(self._step_start_time * 1000),
            },
        )

    def tool_call(self, step: int, tool_name: str, tool_args: dict[str, Any]) -> SSEEvent:
        """Emit event when a tool is being called."""
        return SSEEvent(
            event="tool_call",
            data={
                "step": step,
                "tool": tool_name,
                "args": tool_args,
                "status": "running",
                "timestamp": int(time.time() * 1000),
            },
        )

    def tool_result(
        self, step: int, tool_name: str, result: str, success: bool = True
    ) -> SSEEvent:
        """Emit event when a tool returns a result."""
        duration_ms = None
        if self._step_start_time:
            duration_ms = int((time.time() - self._step_start_time) * 1000)
        return SSEEvent(
            event="tool_result",
            data={
                "step": step,
                "tool": tool_name,
                "result": result[:2000] if len(result) > 2000 else result,
                "success": success,
                "duration_ms": duration_ms,
                "timestamp": int(time.time() * 1000),
            },
        )

    def step_end(self, step: int, status: str = "completed") -> SSEEvent:
        """Emit event when a step completes."""
        duration_ms = None
        if self._step_start_time:
            duration_ms = int((time.time() - self._step_start_time) * 1000)
            self._step_start_time = None
        return SSEEvent(
            event="step_end",
            data={
                "step": step,
                "status": status,
                "duration_ms": duration_ms,
                "timestamp": int(time.time() * 1000),
            },
        )

    def thinking(self, step: int, content: str) -> SSEEvent:
        """Emit event for agent reasoning/thinking."""
        return SSEEvent(
            event="thinking",
            data={
                "step": step,
                "content": content[:1000] if len(content) > 1000 else content,
                "timestamp": int(time.time() * 1000),
            },
        )

    def error(self, step: int, message: str) -> SSEEvent:
        """Emit error event."""
        return SSEEvent(
            event="error",
            data={
                "step": step,
                "message": message,
                "timestamp": int(time.time() * 1000),
            },
        )
