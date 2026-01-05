"""Clarification tool for asking user questions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.models import AgentStatesEnum
from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext


class ClarificationTool(PydanticTool):
    """Ask clarifying questions when facing an ambiguous request.

    Keep all fields concise - brief reasoning, short terms, and clear questions.
    
    In persistent runtime, this tool sets the session state to WAITING_FOR_CLARIFICATION.
    The agent execution completes, and the next user message continues the session.
    """

    reasoning: str = Field(
        description="Why clarification is needed (1-2 sentences MAX)",
        max_length=200,
    )
    unclear_terms: list[str] = Field(
        description="List of unclear terms (brief, 1-3 words each)",
        min_length=1,
        max_length=3,
    )
    assumptions: list[str] = Field(
        description="Possible interpretations (short, 1 sentence each)",
        min_length=2,
        max_length=3,
    )
    questions: list[str] = Field(
        description="3 specific clarifying questions (short and direct)",
        min_length=1,
        max_length=3,
    )

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        # Set state to waiting for clarification
        # In persistent runtime, this signals the session should pause
        context.state = AgentStatesEnum.WAITING_FOR_CLARIFICATION
        context.pending_clarification = self.questions
        context.clarifications_used += 1

        return "\n".join(self.questions)


__all__ = ["ClarificationTool"]

