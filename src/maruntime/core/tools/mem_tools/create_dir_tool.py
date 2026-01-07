"""Tool for creating directories in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class CreateDirTool(PydanticTool):
    """Create a new directory in memory to organize file storage structure.

    Usage: Use to create folders for entities, timeline, preferences, etc.
    """

    reasoning: str = Field(
        description="Why do you need to create this directory? (1-2 sentences MAX)",
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
            os.makedirs(final_path, exist_ok=True)
            return "True"
        except Exception as e:
            return f"Error: {e}"


__all__ = ["CreateDirTool"]

