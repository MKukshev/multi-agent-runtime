from __future__ import annotations

from typing import Any

from platform.core.tools.base_tool import BaseTool
from platform.runtime.router import AgentRouter


class DelegateTemplateTool(BaseTool):
    """Wrapper tool that delegates execution to another agent template."""

    tool_name = "agent.delegate_template"
    description = "Invoke another template by name and return its streamed response."

    def __init__(self, router: AgentRouter) -> None:
        self.router = router

    async def __call__(self, *, task: str) -> dict[str, Any]:
        result = await self.router.route(task)
        aggregated = "".join(chunk.data["choices"][0]["delta"]["content"] for chunk in result.events if chunk.event == "message")
        return {
            "selected_template": result.entry.template.name if result.entry else None,
            "template_version_id": result.entry.version.id if result.entry else None,
            "output": aggregated,
        }


__all__ = ["DelegateTemplateTool"]
