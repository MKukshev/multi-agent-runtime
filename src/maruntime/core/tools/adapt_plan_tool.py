"""Tool for adapting research plans based on new findings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext


class AdaptPlanTool(PydanticTool):
    """Adapt a research plan based on new findings."""

    reasoning: str = Field(description="Why plan needs adaptation based on new data")
    original_goal: str = Field(description="Original research goal")
    new_goal: str = Field(description="Updated research goal")
    plan_changes: list[str] = Field(
        description="Specific changes made to plan",
        min_length=1,
        max_length=3,
    )
    next_steps: list[str] = Field(
        description="Updated remaining steps",
        min_length=2,
        max_length=4,
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


__all__ = ["AdaptPlanTool"]

