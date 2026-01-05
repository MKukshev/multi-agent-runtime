from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generator, Iterable


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """Represents a single SSE event."""

    event: str
    data: dict

    def render(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {payload}\n\n"


class OpenAIStreamingGenerator:
    """Simplified OpenAI-compatible SSE generator."""

    def __init__(self, model: str) -> None:
        self.model = model

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
