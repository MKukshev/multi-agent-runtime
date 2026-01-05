"""Tool for generating research plans."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext


class GeneratePlanTool(PydanticTool):
    """Generate a research plan.

    Useful to split complex request into manageable steps.
    """

    reasoning: str = Field(description="Justification for research approach")
    research_goal: str = Field(description="Primary research objective")
    planned_steps: list[str] = Field(
        description="List of 3-4 planned steps",
        min_length=3,
        max_length=4,
    )
    search_strategies: list[str] = Field(
        description="Information search strategies",
        min_length=2,
        max_length=3,
    )

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        return self.model_dump_json(
            indent=2,
            exclude={"reasoning"},
        )


__all__ = ["GeneratePlanTool"]

