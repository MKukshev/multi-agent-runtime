from __future__ import annotations

from typing import Any, Dict

from platform.core.tools.base_tool import BaseTool


class NextStepTool(BaseTool):
    """Draft tool that proposes the next action for the agent."""

    tool_name = "next_step"
    description = "Suggests the next step based on the current task context."

    async def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        context = kwargs.get("context", "No context provided.")
        return {"next_step": f"Review context and continue research. Context: {context}"}
