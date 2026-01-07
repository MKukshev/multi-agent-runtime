"""Tool for checking directory existence in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class CheckIfDirExistsTool(PydanticTool):
    """Check if a directory exists at the specified path.

    Usage: Use before creating directories to check if they already exist.
    """

    reasoning: str = Field(
        description="Why do you need to check directory existence? (1-2 sentences MAX)",
        max_length=200,
    )
    dir_path: str = Field(description="The path to the directory (relative to memory dir)")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        final_path = os.path.join(MEMORY_PATH, self.dir_path)
        try:
            return str(os.path.exists(final_path) and os.path.isdir(final_path))
        except (OSError, TypeError, ValueError):
            return "False"


__all__ = ["CheckIfDirExistsTool"]

