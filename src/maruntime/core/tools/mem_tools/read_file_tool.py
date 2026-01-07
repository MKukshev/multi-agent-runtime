"""Tool for reading files from agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class ReadFileTool(PydanticTool):
    """Read a file from memory to access stored data.

    Usage: Use to retrieve previously saved agent data.
    """

    reasoning: str = Field(
        description="Why do you need to read this file? (1-2 sentences MAX)",
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
            if not os.path.exists(final_path):
                return f"Error: File {self.file_path} does not exist"

            if not os.path.isfile(final_path):
                return f"Error: {self.file_path} is not a file"

            with open(final_path, "r") as f:
                return f.read()
        except PermissionError:
            return f"Error: Permission denied accessing {self.file_path}"
        except Exception as e:
            return f"Error: {e}"


__all__ = ["ReadFileTool"]

