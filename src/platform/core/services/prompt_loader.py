from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class PromptsConfig:
    """Lightweight prompt configuration container."""

    system_prompt: str = "You are a helpful agent. Available tools:\n{available_tools}"
    initial_user_request: str = "{task}"
    clarification_response: str = "Please clarify: {clarifications}"


class PromptLoader:
    """Utilities for formatting prompts based on available tools."""

    @staticmethod
    def _render_tools(available_tools: Iterable[str]) -> str:
        return "\n".join(f"- {tool}" for tool in available_tools) or "No tools configured."

    @classmethod
    def get_system_prompt(cls, available_tools: Iterable[str], prompts_config: PromptsConfig | None = None) -> str:
        cfg = prompts_config or PromptsConfig()
        return cfg.system_prompt.format(available_tools=cls._render_tools(available_tools))

    @classmethod
    def get_initial_user_request(cls, task: str, prompts_config: PromptsConfig | None = None) -> str:
        cfg = prompts_config or PromptsConfig()
        return cfg.initial_user_request.format(task=task, current_date=_dt.date.today().isoformat())

    @classmethod
    def get_clarification_template(cls, clarifications: str, prompts_config: PromptsConfig | None = None) -> str:
        cfg = prompts_config or PromptsConfig()
        return cfg.clarification_response.format(clarifications=clarifications)
