from __future__ import annotations

import asyncio
from typing import Iterable

from platform.core.agents.simple_agent import SimpleAgent
from platform.core.streaming.openai_sse import SSEEvent


async def run_demo(task: str = "Demo request") -> Iterable[SSEEvent]:
    """Create a simple agent, run one request, and stream SSE events."""
    agent = SimpleAgent(task=task)
    return await agent.run()


def main() -> None:
    events = asyncio.run(run_demo())
    for event in events:
        print(event.render(), end="")


if __name__ == "__main__":  # pragma: no cover - manual execution entrypoint
    main()
