"""Tool for following links between notes in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class GoToLinkTool(PydanticTool):
    """Follow a link in memory and return the content of the linked note.

    Supports Obsidian-style links: [[path/to/note/Y]] reads Y.md

    Usage: Use to navigate between linked notes and entities.
    """

    reasoning: str = Field(
        description="Why do you need to follow this link? (1-2 sentences MAX)",
        max_length=200,
    )
    link_string: str = Field(description="The link string (e.g., [[entities/person]] or path/to/file.md)")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            # Handle Obsidian-style [[link]] format
            if self.link_string.startswith("[[") and self.link_string.endswith("]]"):
                file_path = self.link_string[2:-2]
                if not file_path.endswith(".md"):
                    file_path += ".md"
            else:
                file_path = self.link_string

            final_path = os.path.join(MEMORY_PATH, file_path)

            if not os.path.exists(final_path):
                return f"Error: File {file_path} not found"

            if not os.path.isfile(final_path):
                return f"Error: {file_path} is not a file"

            with open(final_path, "r") as f:
                return f.read()
        except PermissionError:
            return f"Error: Permission denied accessing {self.link_string}"
        except Exception as e:
            return f"Error: {e}"


__all__ = ["GoToLinkTool"]

