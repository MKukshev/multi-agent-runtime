from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Sequence

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from platform.observability import MetricsReporter, get_logger, log_with_correlation
from platform.retrieval.agent_directory import AgentDirectoryEntry, AgentDirectoryService
from platform.retrieval.tool_search import ToolSearchService
from platform.runtime.router import AgentRouter
from platform.runtime.session_service import ChatMessage, SessionService
from platform.runtime.templates import TemplateService
from platform.security import SecurityError, SecurityPolicy


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    top_k: int | None = None


class ModelResponse(BaseModel):
    id: str
    object: str = "model"
    created: int | None = None
    owned_by: str = "runtime"
    version_id: str | None = None


def _extract_task(messages: Sequence[dict[str, Any]]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [item.get("text", "") if isinstance(item, dict) else str(item) for item in content]
        return " ".join(texts)
    return str(content)


def _aggregate_content(events: Iterable[Any]) -> str:
    chunks: list[str] = []
    for event in events:
        if getattr(event, "event", "") != "message":
            continue
        data = getattr(event, "data", {})
        delta = data.get("choices", [{}])[0].get("delta", {})
        if "content" in delta:
            chunks.append(delta["content"])
    return "".join(chunks)


def create_gateway_router(
    session_service: SessionService,
    template_service: TemplateService,
    agent_directory: AgentDirectoryService,
    tool_search: ToolSearchService | None = None,
    *,
    security: SecurityPolicy | None = None,
    metrics: MetricsReporter | None = None,
    logger: logging.Logger | None = None,
) -> APIRouter:
    router = APIRouter()
    metrics = metrics or MetricsReporter()
    logger = logger or get_logger(__name__)
    security = security or SecurityPolicy()
    agent_router = AgentRouter(
        agent_directory,
        session_service=session_service,
        template_service=template_service,
        tool_search_service=tool_search,
    )

    @router.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        metrics.record_request("models")
        configs = await template_service.list_active_models()
        payload = [
            ModelResponse(id=config.template_name, created=None, version_id=config.version_id).model_dump()
            for config in configs
        ]
        log_with_correlation(logger, logging.INFO, "Listed models", session_id=None)
        return {"data": payload}

    async def _entry_for_version(version_id: str) -> AgentDirectoryEntry | None:
        version = await template_service.get_version_with_template(version_id)
        if version is None or version.template is None:
            return None
        return AgentDirectoryEntry(template=version.template, version=version, score=1.0)

    @router.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest) -> Response:
        metrics.record_request("chat.completions", model=request.model)
        task = _extract_task(request.messages)

        session_id: str | None = None
        entry: AgentDirectoryEntry | None = None
        if session_service is not None:
            try:
                session_context, _ = await session_service.resume_session(request.model)
                session_id = request.model
                entry = await _entry_for_version(session_context.template_version_id)
            except ValueError:
                session_id = None

        effective_model = entry.template.name if entry else request.model
        try:
            security.validate(model=effective_model, prompt=task)
        except SecurityError as exc:
            log_with_correlation(logger, logging.WARNING, str(exc), session_id=session_id)
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        result = await agent_router.route(
            task,
            top_k=request.top_k,
            session_id=session_id,
            entry=entry,
        )
        resolved_session = session_id or (result.session_context.session_id if result.session_context else None)
        log_with_correlation(
            logger,
            logging.INFO,
            "chat.completions served",
            session_id=resolved_session,
            model=request.model,
        )

        if request.stream:
            async def event_stream() -> Iterable[str]:
                for event in result.events:
                    if resolved_session:
                        yield f": session_id={resolved_session}\n"
                    yield event.render()

            response = StreamingResponse(event_stream(), media_type="text/event-stream")
            if resolved_session:
                response.headers["x-session-id"] = resolved_session
            metrics.record_completion(model=request.model, status="success", session_id=resolved_session)
            return response

        content = _aggregate_content(result.events)
        response_payload = {
            "id": resolved_session or request.model,
            "object": "chat.completion",
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": ChatMessage.text("assistant", content).model_dump(),
                    "finish_reason": "stop",
                }
            ],
        }
        metrics.record_completion(model=request.model, status="success", session_id=resolved_session)
        headers = {"x-session-id": resolved_session} if resolved_session else None
        return JSONResponse(response_payload, headers=headers)

    return router


__all__ = ["ChatCompletionRequest", "ModelResponse", "create_gateway_router"]
