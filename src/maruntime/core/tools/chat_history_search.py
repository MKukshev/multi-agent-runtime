"""Tool for searching user chat history."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from maruntime.core.models import AgentContext
from maruntime.core.services.chat_memory_service import get_chat_memory_service
from maruntime.core.tools.base_tool import PydanticTool


class ChatHistorySearchTool(PydanticTool):
    """Search through the user's chat history and return relevant Q/A pairs."""

    query: str = Field(description="Search query")
    scope: str = Field(
        default="auto",
        description="'current' for current chat, 'all' for all user chats, 'auto' to use chat scope setting",
    )
    limit: int = Field(default=5, ge=1, le=20, description="Max results to return")
    per_session: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Max results per session",
    )
    context_turns: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Number of turns around the hit to include",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum score threshold",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional override for session ID (if scope is current)",
    )

    def _get_context_value(self, context: AgentContext, key: str) -> Any | None:
        value = getattr(context, key, None)
        if value:
            return value
        custom = getattr(context, "custom_context", None)
        if isinstance(custom, dict):
            return custom.get(key)
        if custom is not None and hasattr(custom, key):
            return getattr(custom, key)
        return None

    def _resolve_scope(self, context: AgentContext) -> str:
        ui_scope = self._get_context_value(context, "search_all_chats")
        if isinstance(ui_scope, bool):
            return "all" if ui_scope else "current"
        if isinstance(ui_scope, str):
            normalized = ui_scope.strip().lower()
            if normalized in {"true", "1", "yes", "all"}:
                return "all"
            if normalized in {"false", "0", "no", "current"}:
                return "current"

        scope = (self.scope or "").strip().lower()
        if not scope or scope == "auto":
            return "all"
        return scope

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        scope = self._resolve_scope(context)
        if scope not in {"all", "current"}:
            return "Error: scope must be 'all' or 'current'"

        user_id = self._get_context_value(context, "user_id")
        if not user_id:
            return "Error: user_id is required for chat history search"

        session_id = None
        if scope == "current":
            session_id = self.session_id or self._get_context_value(context, "session_id")
            if not session_id:
                return "Error: session_id is required for scope='current'"
        elif self.session_id:
            session_id = self.session_id

        chat_memory = get_chat_memory_service()
        results = await chat_memory.search_chats(
            user_id=user_id,
            query=self.query,
            session_id=session_id,
            limit=self.limit,
            per_session=self.per_session,
            min_score=self.min_score,
            context_turns=self.context_turns,
        )

        payload = {
            "query": self.query,
            "scope": scope,
            "limit": self.limit,
            "context_turns": self.context_turns,
            "results": results,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["ChatHistorySearchTool"]
