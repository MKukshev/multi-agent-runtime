from __future__ import annotations

from typing import Any, Iterable, List, Mapping, MutableMapping, Sequence

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from maruntime.persistence import Session as SessionModel
from maruntime.persistence import SessionMessage, SessionRepository


class MessageContent(BaseModel):
    """Represents a single OpenAI message content block."""

    type: str = "text"
    text: str


class ChatMessage(BaseModel):
    """Pydantic model for OpenAI-compatible chat messages."""

    role: str
    content: List[MessageContent] = Field(default_factory=list)
    tool_call_id: str | None = None

    @classmethod
    def text(cls, role: str, text: str, *, tool_call_id: str | None = None) -> "ChatMessage":
        return cls(role=role, content=[MessageContent(text=text)], tool_call_id=tool_call_id)

    @classmethod
    def from_openai(cls, payload: Mapping[str, Any]) -> "ChatMessage":
        role = payload.get("role", "user")
        tool_call_id = payload.get("tool_call_id")
        content_field = payload.get("content")
        if isinstance(content_field, str):
            content_items = [MessageContent(text=content_field)]
        elif isinstance(content_field, list):
            content_items = [MessageContent(**item) if isinstance(item, Mapping) else MessageContent(text=str(item)) for item in content_field]
        elif isinstance(content_field, Mapping):
            content_items = [MessageContent(**content_field)]
        else:
            content_items = []
        return cls(role=role, content=content_items, tool_call_id=tool_call_id)

    def to_openai(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": [item.model_dump() for item in self.content]}
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        return payload


class SessionContext(BaseModel):
    """Encapsulates runtime context for a session."""

    session_id: str
    template_version_id: str
    state: str = "ACTIVE"
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_model(cls, model: SessionModel) -> "SessionContext":
        return cls(
            session_id=model.id,
            template_version_id=model.template_version_id,
            state=model.state,
            data=model.context or {},
        )


class MessageStore(BaseModel):
    """In-memory representation of a session message history."""

    session_id: str
    messages: List[ChatMessage] = Field(default_factory=list)

    def append(self, message: ChatMessage) -> None:
        self.messages.append(message)

    @classmethod
    def from_records(cls, session_id: str, records: Sequence[SessionMessage]) -> "MessageStore":
        messages: List[ChatMessage] = []
        for record in records:
            payload: MutableMapping[str, Any]
            if isinstance(record.content, Mapping):
                payload = dict(record.content)
            else:
                payload = {"content": record.content}
            payload.setdefault("role", record.role)
            if record.tool_call_id and "tool_call_id" not in payload:
                payload["tool_call_id"] = record.tool_call_id
            messages.append(ChatMessage.from_openai(payload))
        return cls(session_id=session_id, messages=messages)

    def to_openai(self) -> list[dict[str, Any]]:
        return [message.to_openai() for message in self.messages]


class SessionService:
    """Service layer for managing session state and message history."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def start_session(
        self, template_version_id: str, *, context: dict[str, Any] | None = None
    ) -> tuple[SessionContext, MessageStore]:
        async with self._session_factory() as session:
            repo = SessionRepository(session)
            session_obj = await repo.create_session(template_version_id=template_version_id, context=context)
            await session.commit()
            return SessionContext.from_model(session_obj), MessageStore(session_id=session_obj.id)

    async def resume_session(self, session_id: str) -> tuple[SessionContext, MessageStore]:
        async with self._session_factory() as session:
            repo = SessionRepository(session)
            session_obj = await repo.get_session(session_id)
            if session_obj is None:
                msg = f"Session {session_id} not found"
                raise ValueError(msg)
            messages = await repo.list_messages(session_id)
            return SessionContext.from_model(session_obj), MessageStore.from_records(session_id, messages)

    async def save_message(self, session_id: str, message: ChatMessage) -> ChatMessage:
        async with self._session_factory() as session:
            repo = SessionRepository(session)
            await repo.add_message(
                session_id=session_id,
                role=message.role,
                content=message.to_openai(),
                tool_call_id=message.tool_call_id,
            )
            await session.commit()
            return message

    async def update_context(self, session_id: str, context: dict[str, Any]) -> SessionContext:
        async with self._session_factory() as session:
            repo = SessionRepository(session)
            session_obj = await repo.update_context(session_id, context)
            if session_obj is None:
                msg = f"Session {session_id} not found"
                raise ValueError(msg)
            await session.commit()
            return SessionContext.from_model(session_obj)

    async def set_state(self, session_id: str, state: str) -> SessionContext:
        async with self._session_factory() as session:
            repo = SessionRepository(session)
            session_obj = await repo.update_state(session_id, state)
            if session_obj is None:
                msg = f"Session {session_id} not found"
                raise ValueError(msg)
            await session.commit()
            return SessionContext.from_model(session_obj)

    async def history(self, session_id: str) -> MessageStore:
        _, store = await self.resume_session(session_id)
        return store
