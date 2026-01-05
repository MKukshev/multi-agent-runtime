"""Final answer tool for completing agent execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from maruntime.core.models import AgentStatesEnum
from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext

logger = logging.getLogger(__name__)


class FinalAnswerTool(PydanticTool):
    """Finalize a task and complete agent execution after all steps are completed.

    Usage: Call after you are ready to finalize your work and provide the final answer to the user.
    """

    reasoning: str = Field(description="Why task is now complete and how answer was verified")
    completed_steps: list[str] = Field(
        description="Summary of completed steps including verification",
        min_length=1,
        max_length=5,
    )
    answer: str = Field(
        description="Comprehensive final answer with EXACT factual details (dates, numbers, names)"
    )
    status: Literal["completed", "failed"] = Field(description="Task completion status")

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        # Update context state based on status
        if self.status == "completed":
            context.state = AgentStatesEnum.COMPLETED
        else:
            context.state = AgentStatesEnum.FAILED

        context.execution_result = self.answer

        logger.info(f"✅ Task {self.status}: {self.answer[:100]}...")

        return self.model_dump_json(indent=2)


__all__ = ["FinalAnswerTool"]

