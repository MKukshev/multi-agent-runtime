"""Prompt loading and formatting utilities.

Provides default prompts based on SGR-agent-core templates and utilities
for rendering prompts with placeholders. Supports loading prompts from
database with fallback to hardcoded defaults.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# Default system prompt based on sgr-agent-core/prompts/system_prompt.txt
DEFAULT_SYSTEM_PROMPT = """<MAIN_TASK_GUIDELINES>
You are an expert assistant with adaptive planning and schema-guided-reasoning capabilities.
You receive tasks from users and need to understand the requirements, determine the appropriate approach, and deliver accurate results.
</MAIN_TASK_GUIDELINES>

<DATE_GUIDELINES>
Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)
PAY ATTENTION TO THE DATE when answering questions about current events or time-sensitive information.
</DATE_GUIDELINES>

<LANGUAGE_GUIDELINES>
Detect the language from user request and use this LANGUAGE for all responses and outputs.
Always respond in the SAME LANGUAGE as the user's request.
</LANGUAGE_GUIDELINES>

<CORE_PRINCIPLES>
1. Assess task complexity: For simple questions, provide direct answers. For complex tasks, create a plan and follow it.
2. Adapt your plan when new data contradicts initial assumptions.
3. Use available tools to gather information and complete tasks.
</CORE_PRINCIPLES>

<AVAILABLE_TOOLS>
{available_tools}
</AVAILABLE_TOOLS>

<TOOL_USAGE_GUIDELINES>
- Use ReasoningTool before other tools to plan your approach
- Use WebSearchTool for current information and facts
- Use ExtractPageContentTool to get full content from URLs found in search
- Use ClarificationTool when the request is ambiguous
- Use FinalAnswerTool to complete the task with your findings
</TOOL_USAGE_GUIDELINES>
"""

# Default initial user request template
DEFAULT_INITIAL_USER_REQUEST = """Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)

USER REQUEST:

{task}
"""

# Default clarification response template  
DEFAULT_CLARIFICATION_RESPONSE = """Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)

USER CLARIFICATION:

{clarifications}

Please continue with your task using this additional information.
"""


@dataclass(slots=True)
class PromptsConfig:
    """Prompt configuration container with sensible defaults.
    
    Prompts support the following placeholders:
    - {available_tools} - List of available tools with descriptions
    - {task} - The user's original task/request
    - {current_date} - Current date and time in ISO format
    - {clarifications} - User's clarification response
    """

    system_prompt: str = field(default=DEFAULT_SYSTEM_PROMPT)
    initial_user_request: str = field(default=DEFAULT_INITIAL_USER_REQUEST)
    clarification_response: str = field(default=DEFAULT_CLARIFICATION_RESPONSE)

    @classmethod
    def from_dict(cls, data: dict[str, str | None]) -> PromptsConfig:
        """Create config from dictionary, using defaults for missing values."""
        return cls(
            system_prompt=data.get("system") or DEFAULT_SYSTEM_PROMPT,
            initial_user_request=data.get("initial_user") or DEFAULT_INITIAL_USER_REQUEST,
            clarification_response=data.get("clarification") or DEFAULT_CLARIFICATION_RESPONSE,
        )

    def merge(self, overrides: dict[str, str | None]) -> PromptsConfig:
        """Create new config with overrides applied (non-None values only)."""
        return PromptsConfig(
            system_prompt=overrides.get("system") or self.system_prompt,
            initial_user_request=overrides.get("initial_user") or self.initial_user_request,
            clarification_response=overrides.get("clarification") or self.clarification_response,
        )


class PromptLoader:
    """Utilities for formatting prompts based on available tools and context."""

    @staticmethod
    def _render_tools(available_tools: Iterable[str]) -> str:
        """Format tool list for prompt insertion."""
        tools_list = list(available_tools)
        if not tools_list:
            return "No tools configured."
        return "\n".join(f"{i}. {tool}" for i, tool in enumerate(tools_list, start=1))

    @staticmethod
    def _current_datetime() -> str:
        """Get current datetime in standard format."""
        return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def get_system_prompt(
        cls,
        available_tools: Iterable[str],
        prompts_config: PromptsConfig | None = None,
    ) -> str:
        """Render system prompt with available tools and current date.
        
        Placeholders:
        - {available_tools} - Formatted list of tools
        - {current_date} - Current datetime
        """
        cfg = prompts_config or PromptsConfig()
        try:
            return cfg.system_prompt.format(
                available_tools=cls._render_tools(available_tools),
                current_date=cls._current_datetime(),
            )
        except KeyError as e:
            # If placeholder is missing, return template as-is with available_tools only
            return cfg.system_prompt.format(
                available_tools=cls._render_tools(available_tools),
            )

    @classmethod
    def get_initial_user_request(
        cls,
        task: str,
        prompts_config: PromptsConfig | None = None,
    ) -> str:
        """Render initial user request with task and current date.
        
        Placeholders:
        - {task} - User's task/request
        - {current_date} - Current datetime
        """
        cfg = prompts_config or PromptsConfig()
        try:
            return cfg.initial_user_request.format(
                task=task,
                current_date=cls._current_datetime(),
            )
        except KeyError as e:
            # Fallback: just return task
            return cfg.initial_user_request.format(task=task)

    @classmethod
    def get_clarification_template(
        cls,
        clarifications: str,
        prompts_config: PromptsConfig | None = None,
    ) -> str:
        """Render clarification response template.
        
        Placeholders:
        - {clarifications} - User's clarification text
        - {current_date} - Current datetime
        """
        cfg = prompts_config or PromptsConfig()
        try:
            return cfg.clarification_response.format(
                clarifications=clarifications,
                current_date=cls._current_datetime(),
            )
        except KeyError as e:
            # Fallback: just return clarifications
            return cfg.clarification_response.format(clarifications=clarifications)


class SystemPromptService:
    """Service for loading system prompts from database.
    
    Provides a unified interface to fetch prompts from the database,
    with automatic fallback to hardcoded defaults if not found.
    """

    # Mapping from DB prompt IDs to PromptsConfig field names
    _ID_TO_FIELD = {
        "system": "system_prompt",
        "initial_user": "initial_user_request",
        "clarification": "clarification_response",
    }

    # Default values for fallback
    _DEFAULTS = {
        "system": DEFAULT_SYSTEM_PROMPT,
        "initial_user": DEFAULT_INITIAL_USER_REQUEST,
        "clarification": DEFAULT_CLARIFICATION_RESPONSE,
    }

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._cache: Optional[dict[str, str]] = None

    async def get_prompts_config(self, use_cache: bool = True) -> PromptsConfig:
        """Load prompts from database and return as PromptsConfig.
        
        Args:
            use_cache: If True, use cached values if available
            
        Returns:
            PromptsConfig with prompts from DB or defaults
        """
        if use_cache and self._cache is not None:
            return self._build_config(self._cache)

        prompts = await self._load_from_db()
        self._cache = prompts
        return self._build_config(prompts)

    async def _load_from_db(self) -> dict[str, str]:
        """Load all active prompts from database."""
        from maruntime.persistence.repositories import SystemPromptRepository

        async with self._session_factory() as session:
            repo = SystemPromptRepository(session)
            return await repo.get_all_as_dict(active_only=True)

    def _build_config(self, db_prompts: dict[str, str]) -> PromptsConfig:
        """Build PromptsConfig from DB prompts with fallbacks."""
        return PromptsConfig(
            system_prompt=db_prompts.get("system", DEFAULT_SYSTEM_PROMPT),
            initial_user_request=db_prompts.get("initial_user", DEFAULT_INITIAL_USER_REQUEST),
            clarification_response=db_prompts.get("clarification", DEFAULT_CLARIFICATION_RESPONSE),
        )

    def invalidate_cache(self) -> None:
        """Clear the cached prompts to force reload on next access."""
        self._cache = None

    @classmethod
    def get_default(cls, prompt_id: str) -> str:
        """Get the hardcoded default for a prompt ID."""
        return cls._DEFAULTS.get(prompt_id, "")

    @classmethod
    def get_all_defaults(cls) -> dict[str, str]:
        """Get all hardcoded defaults as a dictionary."""
        return dict(cls._DEFAULTS)


__all__ = [
    "DEFAULT_CLARIFICATION_RESPONSE",
    "DEFAULT_INITIAL_USER_REQUEST",
    "DEFAULT_SYSTEM_PROMPT",
    "PromptLoader",
    "PromptsConfig",
    "SystemPromptService",
]
