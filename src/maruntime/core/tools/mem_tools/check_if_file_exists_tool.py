"""Tool for checking file existence in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class CheckIfFileExistsTool(PydanticTool):
    """Check if a file exists at the specified path.

    Usage: Use before reading/updating files to verify they exist.
    """

    reasoning: str = Field(
        description="Why do you need to check file existence? (1-2 sentences MAX)",
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
            return str(os.path.exists(final_path) and os.path.isfile(final_path))
        except (OSError, TypeError, ValueError):
            return "False"


__all__ = ["CheckIfFileExistsTool"]

