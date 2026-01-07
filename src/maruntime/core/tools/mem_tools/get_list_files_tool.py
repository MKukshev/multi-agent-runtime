"""Tool for listing files and directories in agent memory."""

import os
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.tools.base_tool import PydanticTool
from maruntime.core.tools.mem_tools.settings import MEMORY_PATH


class GetListFilesTool(PydanticTool):
    """Display all files and directories as a tree structure.

    Example output:
    ```
    ./
    ├── user.md
    └── entities/
        ├── person.md
        └── company.md
    ```

    Usage: Use to see the current organization of stored data.
    """

    reasoning: str = Field(
        description="Why do you need to list files? (1-2 sentences MAX)",
        max_length=200,
    )

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            dir_path = MEMORY_PATH
            
            # Ensure memory directory exists
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                return "./ (empty)"

            def build_tree(start_path: str, prefix: str = "") -> str:
                entries = []
                try:
                    items = sorted(os.listdir(start_path))
                    items = [
                        item
                        for item in items
                        if not item.startswith(".") and item != "__pycache__"
                    ]
                except PermissionError:
                    return f"{prefix}[Permission Denied]\n"

                if not items:
                    return ""

                for i, item in enumerate(items):
                    item_path = os.path.join(start_path, item)
                    is_last_item = i == len(items) - 1

                    if is_last_item:
                        current_prefix = prefix + "└── "
                        extension = prefix + "    "
                    else:
                        current_prefix = prefix + "├── "
                        extension = prefix + "│   "

                    if os.path.isdir(item_path):
                        try:
                            dir_contents = [
                                f
                                for f in os.listdir(item_path)
                                if not f.startswith(".") and f != "__pycache__"
                            ]
                            if not dir_contents:
                                entries.append(f"{current_prefix}{item}/ (empty)\n")
                            else:
                                entries.append(f"{current_prefix}{item}/\n")
                                entries.append(build_tree(item_path, extension))
                        except PermissionError:
                            entries.append(f"{current_prefix}{item}/ [Permission Denied]\n")
                    else:
                        entries.append(f"{current_prefix}{item}\n")

                return "".join(entries)

            tree = f"./\n{build_tree(dir_path)}"
            return tree.rstrip()

        except Exception as e:
            return f"Error: {e}"


__all__ = ["GetListFilesTool"]

