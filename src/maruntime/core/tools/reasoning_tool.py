"""Reasoning tool for agent planning and step-by-step thinking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext


class ReasoningTool(PydanticTool):
    """Agent core logic determines the next reasoning step with adaptive
    planning by schema-guided-reasoning capabilities. Keep all text fields
    concise and focused.

    Usage: Required tool. Use this tool before any other tool execution
    """

    # Reasoning chain - step-by-step thinking process (helps stabilize model)
    reasoning_steps: list[str] = Field(
        description="Step-by-step reasoning (brief, 1 sentence each)",
        min_length=1,
        max_length=10,
    )

    # Reasoning and state assessment
    current_situation: str = Field(
        description="Current research situation (2-3 sentences MAX)",
        max_length=300,
    )
    plan_status: str = Field(
        description="Status of current plan (1 sentence)",
        max_length=150,
    )
    enough_data: bool = Field(
        default=False,
        description="Sufficient data collected for comprehensive report?",
    )

    # Next step planning
    remaining_steps: list[str] = Field(
        default_factory=list,
        description="Remaining steps (empty if task_completed=True)",
        max_length=10,
    )
    task_completed: bool = Field(description="Is the research task finished?")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        return self.model_dump_json(indent=2)


__all__ = ["ReasoningTool"]

