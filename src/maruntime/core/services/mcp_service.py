from __future__ import annotations

from typing import Iterable, List, Type

from maruntime.core.tools.base_tool import MCPBaseTool


class MCPToolBuilder:
    """Placeholder for MCP tool conversion logic."""

    @staticmethod
    def build_tools_from_mcp(names: Iterable[str] | None = None) -> List[Type[MCPBaseTool]]:
        # In this simplified migration the MCP integration is not implemented yet.
        # The function keeps the API surface so callers can extend it later.
        return []
