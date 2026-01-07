"""Tool for getting file or directory size in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class GetSizeTool(PydanticTool):
    """Get the size of a file or directory to monitor memory usage.

    Usage: Use to check how much space is being used.
    """

    reasoning: str = Field(
        description="Why do you need to get size? (1-2 sentences MAX)",
        max_length=200,
    )
    file_or_dir_path: str = Field(
        default="",
        description="The path to file/directory. Empty string returns total memory size.",
    )

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        final_path = os.path.join(MEMORY_PATH, self.file_or_dir_path)

        # If path is empty or just memory path, return total memory size
        if not self.file_or_dir_path or self.file_or_dir_path == "":
            if not os.path.exists(MEMORY_PATH):
                return "0"
            total_size = 0
            for dirpath, _, filenames in os.walk(MEMORY_PATH):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        pass
            return str(total_size)

        if not os.path.exists(final_path):
            return f"Error: Path not found: {self.file_or_dir_path}"

        if os.path.isfile(final_path):
            return str(os.path.getsize(final_path))
        elif os.path.isdir(final_path):
            total_size = 0
            for dirpath, _, filenames in os.walk(final_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        pass
            return str(total_size)
        else:
            return f"Error: Unknown path type: {self.file_or_dir_path}"


__all__ = ["GetSizeTool"]

