"""Tool for updating file contents in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class UpdateFileTool(PydanticTool):
    """Update a file using simple text replacement.

    Performs find-and-replace operation on the file content.

    Usage: Use to modify existing file content.
    """

    reasoning: str = Field(
        description="Why do you need to update this file? (1-2 sentences MAX)",
        max_length=200,
    )
    file_path: str = Field(description="The path to the file (relative to memory dir)")
    old_content: str = Field(description="The exact text to find and replace")
    new_content: str = Field(description="The text to replace old_content with")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        final_path = os.path.join(MEMORY_PATH, self.file_path)
        try:
            if not os.path.exists(final_path):
                return f"Error: File '{self.file_path}' does not exist"

            if not os.path.isfile(final_path):
                return f"Error: '{self.file_path}' is not a file"

            with open(final_path, "r") as f:
                current_content = f.read()

            if self.old_content not in current_content:
                preview_length = 50
                preview = (
                    self.old_content[:preview_length] + "..."
                    if len(self.old_content) > preview_length
                    else self.old_content
                )
                return f"Error: Could not find the specified content. Looking for: '{preview}'"

            occurrences = current_content.count(self.old_content)
            if occurrences > 1:
                return f"Warning: Found {occurrences} occurrences. Replacing only the first one."

            updated_content = current_content.replace(self.old_content, self.new_content, 1)

            if updated_content == current_content:
                return "Error: No changes were made to the file"

            with open(final_path, "w") as f:
                f.write(updated_content)

            return "True"

        except PermissionError:
            return f"Error: Permission denied writing to '{self.file_path}'"
        except Exception as e:
            return f"Error: Unexpected error - {str(e)}"


__all__ = ["UpdateFileTool"]

