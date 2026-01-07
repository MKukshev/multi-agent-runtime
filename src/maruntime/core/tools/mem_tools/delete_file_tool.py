"""Tool for deleting files from agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class DeleteFileTool(PydanticTool):
    """Delete a file from memory to free space or remove outdated data.

    Usage: Use to remove files that are no longer needed.
    """

    reasoning: str = Field(
        description="Why do you need to delete this file? (1-2 sentences MAX)",
        max_length=200,
    )
    file_path: str = Field(description="The path to the file (relative to memory dir)")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        final_path = os.path.join(MEMORY_PATH, self.file_path)
        try:
            os.remove(final_path)
            return "True"
        except FileNotFoundError:
            return f"Error: File {self.file_path} not found"
        except Exception as e:
            return f"Error: {e}"


__all__ = ["DeleteFileTool"]

