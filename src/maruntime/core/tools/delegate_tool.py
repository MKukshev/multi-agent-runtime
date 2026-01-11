"""Delegate tool for invoking other agent templates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from maruntime.runtime.router import AgentRouter


class DelegateTemplateTool(BaseTool):
    """Wrapper tool that delegates execution to another agent template.
    
    Note: This tool uses BaseTool (not PydanticTool) because it requires
    a router instance injected via __init__.
    """

    tool_name = "DelegateTemplateTool"
    description = "Invoke another template by name and return its streamed response."

    def __init__(self, router: AgentRouter) -> None:
        self.router = router

    async def __call__(self, *, task: str, **kwargs: Any) -> dict[str, Any]:
        result = await self.router.route(task)
        aggregated = "".join(
            chunk.data["choices"][0]["delta"]["content"]
            for chunk in result.events
            if chunk.event == "message"
        )
        return {
            "selected_template": result.entry.template.name if result.entry else None,
            "template_version_id": str(result.entry.version.id) if result.entry else None,
            "output": aggregated,
        }


__all__ = ["DelegateTemplateTool"]
