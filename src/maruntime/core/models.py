"""Agent runtime models for context, sources, and search results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from maruntime.runtime.templates import ToolQuota


class SourceData(BaseModel):
    """Data about a research source."""

    number: int = Field(description="Citation number")
    title: str | None = Field(default="Untitled", description="Page title")
    url: str = Field(description="Source URL")
    snippet: str = Field(default="", description="Search snippet or summary")
    full_content: str = Field(default="", description="Full scraped content")
    char_count: int = Field(default=0, description="Character count of full content")

    def __str__(self) -> str:
        return f"[{self.number}] {self.title or 'Untitled'} - {self.url}"


class SearchResult(BaseModel):
    """Search result with query, answer, and sources."""

    query: str = Field(description="Search query")
    answer: str | None = Field(default=None, description="AI-generated answer from search")
    citations: list[SourceData] = Field(default_factory=list, description="List of source citations")
    timestamp: datetime = Field(default_factory=datetime.now, description="Search execution timestamp")

    def __str__(self) -> str:
        return f"Search: '{self.query}' ({len(self.citations)} sources)"


class AgentStatesEnum(str, Enum):
    """Agent execution states."""

    INITED = "inited"
    RESEARCHING = "researching"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    COMPLETED = "completed"
    ERROR = "error"
    FAILED = "failed"

    @classmethod
    def finish_states(cls) -> set[str]:
        return {cls.COMPLETED, cls.FAILED, cls.ERROR}


class ToolUsageStats(BaseModel):
    """Statistics for a single tool's usage in a session."""

    calls: int = Field(default=0, description="Number of calls made")
    last_call_at: datetime | None = Field(default=None, description="Timestamp of last call")
    total_duration_ms: int = Field(default=0, description="Total execution time in ms")
    errors: int = Field(default=0, description="Number of failed calls")


class AgentContext(BaseModel):
    """Runtime context for agent execution.
    
    This is a persistent-friendly version without asyncio.Event.
    State transitions are handled via session state in the database.
    """

    model_config = {"arbitrary_types_allowed": True}

    # Execution state
    state: AgentStatesEnum = Field(default=AgentStatesEnum.INITED, description="Current agent state")
    iteration: int = Field(default=0, description="Current iteration number")
    execution_result: str | None = Field(default=None, description="Final execution result")

    # Reasoning
    current_step_reasoning: Any = Field(default=None, description="Current step reasoning data")

    # Search and sources
    searches: list[SearchResult] = Field(default_factory=list, description="List of performed searches")
    sources: dict[str, SourceData] = Field(default_factory=dict, description="Dictionary of found sources by URL")
    searches_used: int = Field(default=0, description="Number of searches performed")

    # Clarifications (no asyncio.Event - handled via session state)
    clarifications_used: int = Field(default=0, description="Number of clarifications requested")
    pending_clarification: list[str] = Field(default_factory=list, description="Pending clarification questions")

    # Tool usage tracking (per-tool quotas enforcement)
    tool_usage: dict[str, ToolUsageStats] = Field(
        default_factory=dict,
        description="Per-tool usage statistics: {tool_name: ToolUsageStats}"
    )

    # Custom context for extensions
    custom_context: dict | BaseModel | None = Field(
        default=None, description="Custom context for project-specific data"
    )

    def agent_state(self) -> dict[str, Any]:
        """Return serializable agent state (excluding large data)."""
        return self.model_dump(exclude={"searches", "sources"})

    def is_finished(self) -> bool:
        """Check if agent is in a terminal state."""
        return self.state in AgentStatesEnum.finish_states()

    # --- Tool Usage Tracking ---

    def get_tool_calls(self, tool_name: str) -> int:
        """Get number of calls made to a tool."""
        if tool_name in self.tool_usage:
            return self.tool_usage[tool_name].calls
        return 0

    def can_call_tool(self, tool_name: str, quota: ToolQuota | None = None) -> bool:
        """Check if tool can be called based on quota.
        
        Args:
            tool_name: Name of the tool
            quota: Optional ToolQuota with max_calls limit
            
        Returns:
            True if tool can be called, False if quota exceeded
        """
        if quota is None or quota.max_calls is None:
            return True
        return self.get_tool_calls(tool_name) < quota.max_calls

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: int = 0,
        success: bool = True,
    ) -> None:
        """Record a tool call for quota tracking.
        
        Args:
            tool_name: Name of the tool
            duration_ms: Execution duration in milliseconds
            success: Whether the call succeeded
        """
        if tool_name not in self.tool_usage:
            self.tool_usage[tool_name] = ToolUsageStats()

        stats = self.tool_usage[tool_name]
        stats.calls += 1
        stats.last_call_at = datetime.now()
        stats.total_duration_ms += duration_ms
        if not success:
            stats.errors += 1

    def get_remaining_calls(self, tool_name: str, quota: ToolQuota | None = None) -> int | None:
        """Get remaining calls for a tool.
        
        Returns:
            Number of remaining calls, or None if unlimited
        """
        if quota is None or quota.max_calls is None:
            return None
        return max(0, quota.max_calls - self.get_tool_calls(tool_name))

    def get_usage_summary(self) -> dict[str, dict[str, Any]]:
        """Get summary of all tool usage."""
        return {
            name: stats.model_dump()
            for name, stats in self.tool_usage.items()
        }


class ToolExecutionConfig(BaseModel):
    """Default execution limits for a tool (stored in Tool.config.execution)."""

    max_calls: int | None = Field(default=None, description="Default max calls per session")
    timeout: int = Field(default=30, description="Default timeout in seconds")
    cooldown_seconds: float | None = Field(default=None, description="Default delay between calls")
    rate_limit_per_minute: int | None = Field(default=None, description="Max calls per minute")


class ToolConfig(BaseModel):
    """Configuration for a tool instance, loaded from DB."""

    # Common fields
    enabled: bool = Field(default=True, description="Whether tool is enabled")

    # API references (resolved from environment)
    api_key_ref: str | None = Field(default=None, description="Environment variable name for API key")
    api_base_url: str | None = Field(default=None, description="Base URL for API calls")

    # Default execution limits (can be overridden by template.tool_policy.quotas)
    execution: ToolExecutionConfig = Field(
        default_factory=ToolExecutionConfig,
        description="Default execution limits for this tool"
    )

    # Tool-specific settings (arbitrary key-value)
    settings: dict[str, Any] = Field(default_factory=dict, description="Tool-specific settings")

    class Config:
        extra = "allow"  # Allow additional fields for flexibility


__all__ = [
    "AgentContext",
    "AgentStatesEnum",
    "SearchResult",
    "SourceData",
    "ToolConfig",
    "ToolExecutionConfig",
    "ToolUsageStats",
]
