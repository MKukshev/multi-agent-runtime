from __future__ import annotations

from typing import Any, ClassVar, Dict, Iterable, List, Optional, Type, TypeVar

T = TypeVar("T")


class Registry:
    """Simple in-memory registry for agents and tools."""

    _items: ClassVar[Dict[str, Type[Any]]] = {}

    @classmethod
    def register(cls, item: Type[Any], name: Optional[str] = None) -> None:
        key = name or getattr(item, "name", None) or getattr(item, "tool_name", None) or item.__name__
        cls._items[key] = item

    @classmethod
    def get(cls, name: str) -> Type[Any]:
        if name not in cls._items:
            raise KeyError(f"Item '{name}' is not registered in {cls.__name__}")
        return cls._items[name]

    @classmethod
    def resolve(cls, names: Iterable[str | Type[T]]) -> List[Type[T]]:
        resolved: List[Type[T]] = []
        for name in names:
            if isinstance(name, str):
                resolved.append(cls.get(name))  # type: ignore[arg-type]
            else:
                resolved.append(name)
        return resolved

    @classmethod
    def list_items(cls) -> Dict[str, Type[Any]]:
        return dict(cls._items)


class AgentRegistry(Registry):
    """Registry for agent classes."""


class ToolRegistry(Registry):
    """Registry for tool classes."""
