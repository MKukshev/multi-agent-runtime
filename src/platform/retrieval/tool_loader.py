from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field

from platform.core.tools.base_tool import BaseTool
from platform.persistence.models import Tool as ToolModel


class ToolDescriptor(BaseModel):
    """Serializable representation of a tool exposed to the runtime and LLMs."""

    tool_id: str
    name: str
    version: Optional[int] = None
    description: Optional[str] = None
    description_long: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    input_schema: Optional[Dict[str, Any]] = None
    python_entrypoint: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_record(cls, tool: ToolModel) -> "ToolDescriptor":
        """Build a descriptor from a persistence layer record."""

        config = tool.config or {}
        return cls(
            tool_id=tool.id,
            name=tool.name,
            description=tool.description,
            python_entrypoint=tool.python_entrypoint,
            input_schema=config.get("input_schema"),
            config=config,
            is_active=tool.is_active,
        )


class ToolLoader:
    """Load tool classes from catalog descriptors."""

    @staticmethod
    def load_from_entrypoint(entrypoint: str) -> Type[BaseTool]:
        """Resolve and return a tool class from a python entrypoint string."""

        module_path, separator, attribute = entrypoint.partition(":")
        if not module_path or not separator or not attribute:
            raise ValueError(f"Invalid tool entrypoint: {entrypoint!r}")

        module = importlib.import_module(module_path)
        try:
            tool_cls = getattr(module, attribute)
        except AttributeError as exc:  # pragma: no cover - defensive
            raise ImportError(f"Entrypoint '{entrypoint}' not found") from exc

        if not isinstance(tool_cls, type) or not issubclass(tool_cls, BaseTool):
            raise TypeError(f"Loaded object from '{entrypoint}' is not a BaseTool subclass")
        return tool_cls

    @staticmethod
    def resolve_tool(descriptor: ToolDescriptor) -> Type[BaseTool]:
        """Resolve a tool class either via entrypoint or registry lookup."""

        if descriptor.python_entrypoint:
            return ToolLoader.load_from_entrypoint(descriptor.python_entrypoint)

        # Fallback to registry by name
        return BaseTool.tool_registry.get(descriptor.name)

    @staticmethod
    def instantiate(descriptor: ToolDescriptor) -> BaseTool:
        """Create a tool instance from descriptor metadata."""

        tool_cls = ToolLoader.resolve_tool(descriptor)
        return tool_cls()
