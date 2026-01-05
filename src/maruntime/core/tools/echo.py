"""Echo tool for testing and debugging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext


class EchoTool(PydanticTool):
    """Return the payload back to the caller. Useful for testing."""

    message: str = Field(description="Message to echo back")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata to include")

    async def __call__(
        self,
        context: AgentContext | None = None,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        return self.model_dump_json(indent=2)


__all__ = ["EchoTool"]
