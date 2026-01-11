"""Base tool classes for the multi-agent runtime.

Two base classes are provided:
- BaseTool: Simple ABC for tools with custom __init__ (e.g., DelegateTemplateTool)
- PydanticTool: Pydantic-based tool with Field definitions (SGR-style tools)
"""

from __future__ import annotations

import abc
import os
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maruntime.core.services.registry import ToolRegistry

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext, ToolConfig


class ToolRegistryMixin:
    """Mixin that auto-registers tool classes in the global registry."""

    tool_registry: ClassVar[type[ToolRegistry]] = ToolRegistry

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Register every subclass except the abstract base classes."""
        super().__init_subclass__(**kwargs)
        excluded = {"BaseTool", "MCPBaseTool", "PydanticTool", "MCPPydanticTool"}
        if abc.ABC not in cls.__bases__ and cls.__name__ not in excluded:
            cls.tool_registry.register(cls)


class ToolConfigResolver:
    """Resolves tool configuration, replacing *_ref fields with env values."""

    @staticmethod
    def resolve(config: dict[str, Any] | None) -> dict[str, Any]:
        """Resolve configuration, replacing *_ref fields with environment values.
        
        Example:
            {"api_key_ref": "TAVILY_API_KEY"} -> {"api_key": "actual-key-value"}
        """
        if not config:
            return {}

        resolved = {}
        for key, value in config.items():
            if key.endswith("_ref") and isinstance(value, str):
                # Replace _ref suffix and resolve from environment
                resolved_key = key[:-4]  # Remove "_ref"
                resolved[resolved_key] = os.getenv(value, "")
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def get_api_key(config: dict[str, Any], default_env: str = "OPENAI_API_KEY") -> str | None:
        """Get API key from config or default environment variable."""
        if "api_key" in config:
            return config["api_key"]
        if "api_key_ref" in config:
            return os.getenv(config["api_key_ref"])
        return os.getenv(default_env)


class BaseTool(ToolRegistryMixin, abc.ABC):
    """Base contract for synchronous/asynchronous tools.
    
    Use this for tools that need custom __init__ with dependencies.
    For Pydantic-based tools with Field definitions, use PydanticTool.
    """

    tool_name: ClassVar[str | None] = None
    description: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Prepare default metadata and register subclasses."""
        super().__init_subclass__(**kwargs)
        if cls.__name__ in {"BaseTool", "MCPBaseTool"}:
            return
        cls.tool_name = cls.tool_name or cls.__name__
        cls.description = cls.description or (cls.__doc__ or "")

    @abc.abstractmethod
    async def __call__(self, **kwargs: Any) -> Any:
        """Execute the tool."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} tool_name={self.tool_name}>"


class MCPBaseTool(BaseTool):
    """Base class for MCP (Model Context Protocol) backed tools."""

    mcp_name: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure MCP tools keep tool naming parity."""
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "MCPBaseTool":
            return
        cls.mcp_name = cls.mcp_name or cls.tool_name


class PydanticTool(BaseModel, ToolRegistryMixin):
    """Pydantic-based tool with Field definitions (SGR-style).
    
    Use this for tools that define their parameters as Pydantic Fields.
    The tool receives context and config when called.
    
    Example:
        class ReasoningTool(PydanticTool):
            reasoning_steps: list[str] = Field(description="Step-by-step reasoning")
            
            async def __call__(self, context: AgentContext, config: dict, **_) -> str:
                return self.model_dump_json()
    """

    tool_name: ClassVar[str | None] = None
    description: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Prepare default metadata and register subclasses."""
        super().__init_subclass__(**kwargs)
        excluded = {"PydanticTool", "MCPPydanticTool"}
        if cls.__name__ in excluded:
            return
        cls.tool_name = cls.tool_name or cls.__name__
        cls.description = cls.description or (cls.__doc__ or "")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | ToolConfig | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute the tool. Override in subclasses."""
        raise NotImplementedError("PydanticTool subclasses must implement __call__")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} tool_name={self.tool_name}>"


class MCPPydanticTool(PydanticTool):
    """Pydantic-based MCP tool."""

    mcp_name: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure MCP tools keep tool naming parity."""
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "MCPPydanticTool":
            return
        cls.mcp_name = cls.mcp_name or cls.tool_name


__all__ = [
    "BaseTool",
    "MCPBaseTool",
    "PydanticTool",
    "MCPPydanticTool",
    "ToolConfigResolver",
    "ToolRegistryMixin",
]
