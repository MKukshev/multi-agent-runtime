from __future__ import annotations

from typing import Any, Dict, Optional

from platform.core.tools.base_tool import BaseTool
from platform.persistence.repositories import SessionRepository


class ToolExecutor:
    """Execute tools while persisting execution metadata."""

    def __init__(self, session_repository: SessionRepository):
        self.session_repository = session_repository

    async def execute(
        self,
        tool: BaseTool,
        session_id: str,
        *,
        tool_id: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Any:
        args = arguments or {}
        execution = await self.session_repository.log_tool_execution(
            session_id,
            tool_name=tool.tool_name or tool.__class__.__name__,
            tool_id=tool_id,
            arguments=args,
            status="RUNNING",
        )

        try:
            result = await tool(**args)
            execution.result = result
            execution.status = "SUCCESS"
            return result
        except Exception as exc:  # pragma: no cover - defensive path
            execution.result = {"error": str(exc)}
            execution.status = "FAILED"
            raise
        finally:
            await self.session_repository.session.flush()


__all__ = ["ToolExecutor"]
