from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsReporter:
    """In-memory metrics collector for the gateway."""

    counters: Counter = field(default_factory=Counter)

    def record_request(self, endpoint: str, *, model: str | None = None) -> None:
        self.counters[f"{endpoint}.requests"] += 1
        if model:
            self.counters[f"{endpoint}.requests.model.{model}"] += 1

    def record_completion(self, *, model: str, status: str, session_id: str | None = None) -> None:
        key = f"chat.completions.status.{status}"
        self.counters[key] += 1
        self.counters[f"chat.completions.model.{model}"] += 1
        if session_id:
            self.counters[f"chat.completions.session.{session_id}"] += 1

    def snapshot(self) -> dict[str, Any]:
        return dict(self.counters)


__all__ = ["MetricsReporter"]
