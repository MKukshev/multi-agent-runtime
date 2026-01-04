from __future__ import annotations

from typing import Any

from platform.core.tools.base_tool import BaseTool


class EchoTool(BaseTool):
    """Return the payload back to the caller."""

    tool_name = "echo"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        return {"echo": kwargs}
