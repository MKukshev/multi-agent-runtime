"""Tool for creating files in agent memory."""

import os
import uuid
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH
from maruntime.core.tools.mem_tools.utils import check_size_limits


class CreateFileTool(PydanticTool):
    """Create a new file in memory with specified content.

    Creates a temporary file first, checks size limits, then moves to final location.

    Usage: Use to save agent data to persistent storage.
    """

    reasoning: str = Field(
        description="Why do you need to create this file? (1-2 sentences MAX)",
        max_length=200,
    )
    file_path: str = Field(description="The path to the file (relative to memory dir)")
    content: str = Field(description="The content of the file")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        final_path = os.path.join(MEMORY_PATH, self.file_path)
        temp_file_path = None
        try:
            # Ensure memory directory exists
            os.makedirs(MEMORY_PATH, exist_ok=True)
            
            parent_dir = os.path.dirname(final_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            target_dir = os.path.dirname(os.path.abspath(final_path)) or "."
            temp_file_path = os.path.join(target_dir, f"temp_{uuid.uuid4().hex[:8]}.txt")

            with open(temp_file_path, "w") as f:
                f.write(self.content)

            if check_size_limits(temp_file_path):
                with open(final_path, "w") as f:
                    f.write(self.content)
                os.remove(temp_file_path)
                return "True"
            else:
                os.remove(temp_file_path)
                return f"Error: File {self.file_path} is too large to create"
        except Exception as e:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
            return f"Error creating file {self.file_path}: {e}"


__all__ = ["CreateFileTool"]

