from __future__ import annotations

import abc
from typing import Any, ClassVar

from platform.core.services.registry import ToolRegistry


class ToolRegistryMixin:
    """Mixin that auto-registers tool classes in the global registry."""

    tool_registry: ClassVar[ToolRegistry] = ToolRegistry

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401
        """Register every subclass except the abstract base classes."""
        super().__init_subclass__(**kwargs)
        if not abc.ABC in cls.__bases__ and cls.__name__ not in {"BaseTool", "MCPBaseTool"}:
            cls.tool_registry.register(cls)


class BaseTool(ToolRegistryMixin, abc.ABC):
    """Base contract for synchronous/asynchronous tools."""

    tool_name: ClassVar[str | None] = None
    description: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401
        """Prepare default metadata and register subclasses."""
        super().__init_subclass__(**kwargs)
        if cls is BaseTool:
            return
        cls.tool_name = cls.tool_name or cls.__name__.lower()
        cls.description = cls.description or (cls.__doc__ or "")

    @abc.abstractmethod
    async def __call__(self, **kwargs: Any) -> Any:
        """Execute the tool."""

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.__class__.__name__} tool_name={self.tool_name}>"


class MCPBaseTool(BaseTool):
    """Base class for MCP (Model Context Protocol) backed tools."""

    mcp_name: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401
        """Ensure MCP tools keep tool naming parity."""
        super().__init_subclass__(**kwargs)
        if cls is MCPBaseTool:
            return
        cls.mcp_name = cls.mcp_name or cls.tool_name
