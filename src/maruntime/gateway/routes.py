from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable, Sequence

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from openai import APIConnectionError, APIStatusError, AuthenticationError, OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from maruntime.core.services.chat_memory_service import get_chat_memory_service
from maruntime.observability import MetricsReporter, get_logger, log_with_correlation
from maruntime.persistence.repositories import AgentInstanceRepository, SessionRepository
from maruntime.retrieval.agent_directory import AgentDirectoryEntry, AgentDirectoryService
from maruntime.retrieval.tool_search import ToolSearchService
from maruntime.runtime.router import AgentRouter
from maruntime.runtime.session_service import ChatMessage, SessionService
from maruntime.runtime.templates import TemplateService
from maruntime.security import SecurityError, SecurityPolicy


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    top_k: int | None = None
    chat_id: str | None = None  # Optional: continue existing chat
    search_all_chats: bool = Field(
        default=False,
        description="Search scope for chat memory (false=current chat, true=all chats)",
    )


class ModelResponse(BaseModel):
    id: str
    object: str = "model"
    created: int | None = None
    owned_by: str = "runtime"
    version_id: str | None = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    model: str | None
    state: str
    created_at: str
    updated_at: str


class CreateChatRequest(BaseModel):
    model: str
    title: str | None = None


class UpdateChatRequest(BaseModel):
    title: str


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


async def _aggregate_content(events: AsyncGenerator[Any, None]) -> str:
    """Aggregate content from async event generator (for non-streaming responses)."""
    chunks: list[str] = []
    async for event in events:
        if getattr(event, "event", "") != "message":
            continue
        data = getattr(event, "data", {})
        delta = data.get("choices", [{}])[0].get("delta", {})
        if "content" in delta:
            chunks.append(delta["content"])
    return "".join(chunks)


async def _error_stream(error_message: str, error_type: str = "llm_error") -> AsyncGenerator[str, None]:
    """Generate SSE error event stream for client."""
    error_event = {
        "event": "error",
        "data": {
            "error": error_message,
            "type": error_type,
        }
    }
    yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
    yield "data: [DONE]\n\n"


def _format_llm_error(exc: Exception) -> tuple[str, str, int]:
    """Format LLM exception into user-friendly message, error type, and HTTP status code."""
    if isinstance(exc, APIConnectionError):
        return (
            f"Модель недоступна: не удалось подключиться к LLM серверу. Проверьте, что сервер запущен. ({exc})",
            "connection_error",
            503,
        )
    if isinstance(exc, AuthenticationError):
        return (
            f"Ошибка аутентификации LLM: неверный API ключ. ({exc})",
            "auth_error",
            401,
        )
    if isinstance(exc, APIStatusError):
        return (
            f"Ошибка LLM API (статус {exc.status_code}): {exc.message}",
            "api_error",
            502,
        )
    if isinstance(exc, OpenAIError):
        return (
            f"Ошибка LLM: {exc}",
            "llm_error",
            500,
        )
    return (
        f"Внутренняя ошибка агента: {exc}",
        "internal_error",
        500,
    )


def create_gateway_router(
    session_service: SessionService,
    template_service: TemplateService,
    agent_directory: AgentDirectoryService,
    tool_search: ToolSearchService | None = None,
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
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
    _session_factory = session_factory

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

    async def _entry_for_model(model_name: str) -> AgentDirectoryEntry | None:
        """Get entry by exact template name match."""
        # Get all active models and find exact match
        configs = await template_service.list_active_models()
        for config in configs:
            if config.template_name == model_name:
                version = await template_service.get_version_with_template(config.version_id)
                if version and version.template:
                    return AgentDirectoryEntry(template=version.template, version=version, score=1.0)
        return None

    @router.post("/v1/chat/completions")
    async def chat_completions(request: Request, body: ChatCompletionRequest) -> Response:
        metrics.record_request("chat.completions", model=body.model)
        task = _extract_task(body.messages)

        # Get authenticated user (optional for backwards compatibility)
        user = getattr(request.state, 'user', None)
        user_id = user.id if user else None
        search_all_chats = bool(body.search_all_chats)
        context_data = {"search_all_chats": search_all_chats}

        session_id: str | None = body.chat_id  # Use provided chat_id if available
        entry: AgentDirectoryEntry | None = None
        claimed_instance_id: str | None = None

        # If chat_id provided, validate ownership and get entry
        if session_id and _session_factory and user_id:
            async with _session_factory() as db_session:
                session_repo = SessionRepository(db_session)
                sess = await session_repo.get_session(session_id)
                if sess:
                    if sess.user_id and sess.user_id != user_id:
                        raise HTTPException(status_code=403, detail="Access denied to this chat")
                    entry = await _entry_for_version(sess.template_version_id)
                else:
                    session_id = None  # Chat not found, will create new

        # Try to resume session by model name (legacy behavior)
        if session_id is None and session_service is not None:
            try:
                session_context, _ = await session_service.resume_session(body.model)
                session_id = body.model
                entry = await _entry_for_version(session_context.template_version_id)
            except ValueError:
                session_id = None

        # If no entry from session resume, try to get entry by exact model name match (for new sessions)
        if entry is None:
            entry = await _entry_for_model(body.model)

        if _session_factory and session_id:
            async with _session_factory() as db_session:
                session_repo = SessionRepository(db_session)
                sess = await session_repo.get_session(session_id)
                if sess:
                    context = dict(sess.context or {})
                    context["search_all_chats"] = search_all_chats
                    await session_repo.update_context(session_id, context)
                    await db_session.commit()

        effective_model = entry.template.name if entry else body.model
        try:
            security.validate(model=effective_model, prompt=task)
        except SecurityError as exc:
            log_with_correlation(logger, logging.WARNING, str(exc), session_id=session_id)
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        # Try to claim an available instance for this template
        if _session_factory and entry and entry.template:
            async with _session_factory() as db_session:
                instance_repo = AgentInstanceRepository(db_session)
                instance = await instance_repo.get_idle_instance_for_template(entry.template.id)
                if instance:
                    log_with_correlation(
                        logger,
                        logging.INFO,
                        f"Claiming instance {instance.name} for template {entry.template.name}",
                        session_id=session_id,
                    )
                    claimed_instance_id = instance.id
                    # Note: actual claim happens after session is created

        result = await agent_router.route(
            task,
            top_k=body.top_k,
            session_id=session_id,
            entry=entry,
            user_id=user_id,  # Pass user_id for new session creation
            context_data=context_data if session_id is None else None,
        )
        resolved_session = session_id or (result.session_context.session_id if result.session_context else None)

        # Claim the instance and link to session
        if _session_factory and claimed_instance_id and resolved_session:
            async with _session_factory() as db_session:
                instance_repo = AgentInstanceRepository(db_session)
                session_repo = SessionRepository(db_session)
                # Claim instance (set status to BUSY)
                await instance_repo.claim_session(claimed_instance_id, resolved_session)
                # Link session to instance
                await session_repo.set_instance(resolved_session, claimed_instance_id)
                await db_session.commit()
                log_with_correlation(
                    logger,
                    logging.INFO,
                    f"Instance claimed for session",
                    session_id=resolved_session,
                    instance_id=claimed_instance_id,
                )

        log_with_correlation(
            logger,
            logging.INFO,
            "chat.completions served",
            session_id=resolved_session,
            model=body.model,
        )

        # Link session to user if authenticated
        if _session_factory and user_id and resolved_session:
            async with _session_factory() as db_session:
                session_repo = SessionRepository(db_session)
                await session_repo.set_user(resolved_session, user_id)
                await db_session.commit()

        # Release the instance after completion
        async def release_instance() -> None:
            if _session_factory and claimed_instance_id:
                async with _session_factory() as db_session:
                    instance_repo = AgentInstanceRepository(db_session)
                    await instance_repo.release_session(claimed_instance_id)
                    # Increment stats
                    await instance_repo.increment_stats(
                        claimed_instance_id,
                        messages=len(body.messages) + 1,  # input + output
                    )
                    await db_session.commit()

        if body.stream:
            # Capture variables for closure
            _user_id = user_id
            _user = user
            _resolved_session = resolved_session
            _model = body.model
            _messages = body.messages
            _result = result  # Keep reference to get session_context later
            
            async def event_stream() -> AsyncGenerator[str, None]:
                nonlocal _resolved_session
                accumulated_content: list[str] = []
                try:
                    async for event in result.events:
                        # Update session_id dynamically from agent's session_context
                        if not _resolved_session:
                            session_ctx = _result.get_session_context()
                            if session_ctx:
                                _resolved_session = session_ctx.session_id
                        
                        if _resolved_session:
                            yield f": session_id={_resolved_session}\n"
                        yield event.render()
                        
                        # Accumulate message content
                        if getattr(event, "event", "") == "message":
                            data = getattr(event, "data", {})
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta:
                                accumulated_content.append(delta["content"])
                except (APIConnectionError, AuthenticationError, APIStatusError, OpenAIError) as exc:
                    error_msg, error_type, _ = _format_llm_error(exc)
                    log_with_correlation(logger, logging.ERROR, error_msg, session_id=_resolved_session)
                    async for chunk in _error_stream(error_msg, error_type):
                        yield chunk
                    return
                except Exception as exc:
                    error_msg = f"Внутренняя ошибка агента: {exc}"
                    log_with_correlation(logger, logging.ERROR, error_msg, session_id=_resolved_session)
                    async for chunk in _error_stream(error_msg, "internal_error"):
                        yield chunk
                    return
                finally:
                    await release_instance()
                    
                    # Save to chat memory after streaming completes
                    if _user_id and _resolved_session:
                        chat_memory = get_chat_memory_service()
                        user_name = getattr(_user, 'display_name', None) if _user else None
                        
                        # Save user message
                        last_user_msg = _messages[-1] if _messages else None
                        if last_user_msg and last_user_msg.get("role") == "user":
                            user_content = last_user_msg.get("content", "")
                            if isinstance(user_content, list):
                                user_content = " ".join(
                                    item.get("text", "") if isinstance(item, dict) else str(item)
                                    for item in user_content
                                )
                            await chat_memory.save_message(
                                user_id=_user_id,
                                session_id=_resolved_session,
                                role="user",
                                content=user_content,
                                user_name=user_name,
                                model_name=_model,
                            )
                        
                        # Save assistant response
                        final_content = "".join(accumulated_content) or "Task completed."
                        await chat_memory.save_message(
                            user_id=_user_id,
                            session_id=_resolved_session,
                            role="assistant",
                            content=final_content,
                            agent_name=_model,
                            model_name=_model,
                        )

            response = StreamingResponse(event_stream(), media_type="text/event-stream")
            if resolved_session:
                response.headers["x-session-id"] = resolved_session
            if claimed_instance_id:
                response.headers["x-instance-id"] = claimed_instance_id
            metrics.record_completion(model=body.model, status="success", session_id=resolved_session)
            return response

        # Release instance for non-streaming
        await release_instance()

        try:
            content = await _aggregate_content(result.events)
        except (APIConnectionError, AuthenticationError, APIStatusError, OpenAIError) as exc:
            error_msg, error_type, status_code = _format_llm_error(exc)
            log_with_correlation(logger, logging.ERROR, error_msg, session_id=resolved_session)
            metrics.record_completion(model=body.model, status="error", session_id=resolved_session)
            raise HTTPException(status_code=status_code, detail=error_msg) from exc
        except Exception as exc:
            error_msg = f"Внутренняя ошибка агента: {exc}"
            log_with_correlation(logger, logging.ERROR, error_msg, session_id=resolved_session)
            metrics.record_completion(model=body.model, status="error", session_id=resolved_session)
            raise HTTPException(status_code=500, detail=error_msg) from exc
        
        # Update resolved_session after agent execution (session is created during execution)
        session_ctx = result.get_session_context()
        if not resolved_session and session_ctx:
            resolved_session = session_ctx.session_id
        
        # Save messages to chat memory
        if user_id and resolved_session:
            chat_memory = get_chat_memory_service()
            user_name = getattr(user, 'display_name', None) if user else None
            
            # Get last user message
            last_user_msg = body.messages[-1] if body.messages else None
            if last_user_msg and last_user_msg.get("role") == "user":
                user_content = last_user_msg.get("content", "")
                if isinstance(user_content, list):
                    user_content = " ".join(
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in user_content
                    )
                await chat_memory.save_message(
                    user_id=user_id,
                    session_id=resolved_session,
                    role="user",
                    content=user_content,
                    user_name=user_name,
                    model_name=body.model,
                )
            
            # Save assistant response
            await chat_memory.save_message(
                user_id=user_id,
                session_id=resolved_session,
                role="assistant",
                content=content,
                agent_name=body.model,
                model_name=body.model,
            )
        
        response_payload = {
            "id": resolved_session or body.model,
            "object": "chat.completion",
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": ChatMessage.text("assistant", content).model_dump(),
                    "finish_reason": "stop",
                }
            ],
        }
        metrics.record_completion(model=body.model, status="success", session_id=resolved_session)
        headers = {"x-session-id": resolved_session} if resolved_session else {}
        if claimed_instance_id:
            headers["x-instance-id"] = claimed_instance_id
        return JSONResponse(response_payload, headers=headers if headers else None)

    # ==================== Chat Management API ====================

    @router.get("/v1/chats")
    async def list_user_chats(request: Request) -> dict[str, Any]:
        """List all chats for the authenticated user."""
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not _session_factory:
            raise HTTPException(status_code=500, detail="Database not configured")

        async with _session_factory() as db_session:
            session_repo = SessionRepository(db_session)
            sessions = await session_repo.list_user_sessions(user.id)
            
            chats = []
            for sess in sessions:
                # Get model name from template service
                model_name = None
                try:
                    version = await template_service.get_version_with_template(sess.template_version_id)
                    if version and version.template:
                        model_name = version.template.name
                except Exception:
                    pass
                
                chats.append(ChatSessionResponse(
                    id=sess.id,
                    title=sess.title or "New Chat",
                    model=model_name,
                    state=sess.state,
                    created_at=sess.created_at.isoformat() if sess.created_at else "",
                    updated_at=sess.updated_at.isoformat() if sess.updated_at else "",
                ).model_dump())

        return {"data": chats}

    @router.post("/v1/chats")
    async def create_chat(request: Request, body: CreateChatRequest) -> ChatSessionResponse:
        """Create a new chat session for the authenticated user."""
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not _session_factory:
            raise HTTPException(status_code=500, detail="Database not configured")

        # Find template version for the model
        entry = await _entry_for_model(body.model)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Model '{body.model}' not found")

        async with _session_factory() as db_session:
            session_repo = SessionRepository(db_session)
            sess = await session_repo.create_session(
                template_version_id=entry.version.id,
                user_id=user.id,
                title=body.title or "New Chat",
            )
            await db_session.commit()

            return ChatSessionResponse(
                id=sess.id,
                title=sess.title or "New Chat",
                model=body.model,
                state=sess.state,
                created_at=sess.created_at.isoformat() if sess.created_at else "",
                updated_at=sess.updated_at.isoformat() if sess.updated_at else "",
            )

    @router.get("/v1/chats/{chat_id}")
    async def get_chat(request: Request, chat_id: str) -> ChatSessionResponse:
        """Get a specific chat by ID."""
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not _session_factory:
            raise HTTPException(status_code=500, detail="Database not configured")

        async with _session_factory() as db_session:
            session_repo = SessionRepository(db_session)
            sess = await session_repo.get_session(chat_id)
            
            if not sess:
                raise HTTPException(status_code=404, detail="Chat not found")
            
            if sess.user_id != user.id:
                raise HTTPException(status_code=403, detail="Access denied")

            # Get model name from template service
            model_name = None
            try:
                version = await template_service.get_version_with_template(sess.template_version_id)
                if version and version.template:
                    model_name = version.template.name
            except Exception:
                pass

            return ChatSessionResponse(
                id=sess.id,
                title=sess.title or "New Chat",
                model=model_name,
                state=sess.state,
                created_at=sess.created_at.isoformat() if sess.created_at else "",
                updated_at=sess.updated_at.isoformat() if sess.updated_at else "",
            )

    @router.put("/v1/chats/{chat_id}")
    async def update_chat(request: Request, chat_id: str, body: UpdateChatRequest) -> ChatSessionResponse:
        """Update chat title."""
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not _session_factory:
            raise HTTPException(status_code=500, detail="Database not configured")

        async with _session_factory() as db_session:
            session_repo = SessionRepository(db_session)
            sess = await session_repo.get_session(chat_id)
            
            if not sess:
                raise HTTPException(status_code=404, detail="Chat not found")
            
            if sess.user_id != user.id:
                raise HTTPException(status_code=403, detail="Access denied")

            template_version_id = sess.template_version_id
            sess = await session_repo.update_title(chat_id, body.title)
            await db_session.commit()

            # Get model name from template service
            model_name = None
            try:
                version = await template_service.get_version_with_template(template_version_id)
                if version and version.template:
                    model_name = version.template.name
            except Exception:
                pass

            return ChatSessionResponse(
                id=sess.id,
                title=sess.title or "New Chat",
                model=model_name,
                state=sess.state,
                created_at=sess.created_at.isoformat() if sess.created_at else "",
                updated_at=sess.updated_at.isoformat() if sess.updated_at else "",
            )

    @router.delete("/v1/chats/{chat_id}")
    async def delete_chat(request: Request, chat_id: str) -> dict[str, str]:
        """Delete a chat."""
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not _session_factory:
            raise HTTPException(status_code=500, detail="Database not configured")

        async with _session_factory() as db_session:
            session_repo = SessionRepository(db_session)
            sess = await session_repo.get_session(chat_id)
            
            if not sess:
                raise HTTPException(status_code=404, detail="Chat not found")
            
            if sess.user_id != user.id:
                raise HTTPException(status_code=403, detail="Access denied")

            await session_repo.delete_session(chat_id)
            await db_session.commit()

        return {"message": "Chat deleted successfully"}

    @router.get("/v1/chats/{chat_id}/messages")
    async def get_chat_messages(request: Request, chat_id: str) -> dict[str, Any]:
        """Get messages for a chat including agent steps."""
        user = getattr(request.state, 'user', None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not _session_factory:
            raise HTTPException(status_code=500, detail="Database not configured")

        async with _session_factory() as db_session:
            session_repo = SessionRepository(db_session)
            sess = await session_repo.get_session(chat_id)
            
            if not sess:
                raise HTTPException(status_code=404, detail="Chat not found")
            
            if sess.user_id != user.id:
                raise HTTPException(status_code=403, detail="Access denied")

            messages = await session_repo.list_messages(chat_id)
            
            result = []
            for msg in messages:
                message_type = getattr(msg, 'message_type', 'message') or 'message'
                
                # Skip system prompts (role=system AND type=message), but keep agent steps
                if msg.role == "system" and message_type == "message":
                    continue
                    
                entry = {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "message_type": message_type,
                    "step_number": getattr(msg, 'step_number', None),
                    "step_data": getattr(msg, 'step_data', None),
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                }
                result.append(entry)
            
            return {"data": result}

    return router


__all__ = ["ChatCompletionRequest", "ModelResponse", "ChatSessionResponse", "create_gateway_router"]
