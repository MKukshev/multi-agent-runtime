"""SQLAlchemy ORM models for the platform persistence layer.

This module defines the core relational schema used by the runtime to store
tools, templates, sessions, executions, and related artifacts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship


Base = declarative_base()


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    python_entrypoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tool_executions: Mapped[List["ToolExecution"]] = relationship(
        back_populates="tool", cascade="all, delete-orphan"
    )


class AgentTemplate(Base):
    __tablename__ = "agent_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("template_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    versions: Mapped[List["TemplateVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", foreign_keys="TemplateVersion.template_id"
    )
    active_version: Mapped[Optional["TemplateVersion"]] = relationship(
        "TemplateVersion", foreign_keys=[active_version_id], post_update=True
    )
    agent_instances: Mapped[List["AgentInstance"]] = relationship(
        "AgentInstance", back_populates="template", cascade="all, delete-orphan"
    )


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_templates.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    template: Mapped[AgentTemplate] = relationship(
        "AgentTemplate", back_populates="versions", foreign_keys=[template_id]
    )
    sessions: Mapped[List["Session"]] = relationship(
        back_populates="template_version", cascade="all, delete-orphan"
    )
    agent_instances: Mapped[List["AgentInstance"]] = relationship(
        back_populates="template_version", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    template_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("template_versions.id"), nullable=False
    )
    # Link to the instance that processed this session
    instance_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("agent_instances.id", use_alter=True, name="fk_session_instance"),
        nullable=True
    )
    state: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    template_version: Mapped[TemplateVersion] = relationship("TemplateVersion", back_populates="sessions")
    instance: Mapped[Optional["AgentInstance"]] = relationship(
        "AgentInstance",
        back_populates="sessions",
        foreign_keys=[instance_id]
    )
    messages: Mapped[List["SessionMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    tool_executions: Mapped[List["ToolExecution"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    sources: Mapped[List["Source"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    artifacts: Mapped[List["Artifact"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionMessage(Base):
    __tablename__ = "session_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    session: Mapped[Session] = relationship("Session", back_populates="messages")


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=False)
    tool_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tools.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    session: Mapped[Session] = relationship("Session", back_populates="tool_executions")
    tool: Mapped[Optional[Tool]] = relationship("Tool", back_populates="tool_executions")


class AgentInstance(Base):
    """Named agent instance (slot) that can process sessions sequentially.
    
    Represents a persistent worker bound to a template. Can be started/stopped
    and processes one session at a time. Supports monitoring and statistics.
    
    Statuses:
    - OFFLINE: Not running, disabled or stopped
    - STARTING: Being initialized
    - IDLE: Running, waiting for a session
    - BUSY: Processing a session
    - ERROR: In error state, needs attention
    - STOPPING: Shutting down
    """
    __tablename__ = "agent_instances"

    # Identity
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Template binding
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_templates.id"), nullable=False)
    template_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("template_versions.id"), nullable=False
    )

    # State
    status: Mapped[str] = mapped_column(String(50), default="OFFLINE")
    current_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sessions.id", use_alter=True, name="fk_instance_current_session"),
        nullable=True
    )

    # Configuration
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    config_overrides: Mapped[dict] = mapped_column(JSON, default=dict)

    # Statistics
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Lifecycle
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    template: Mapped[AgentTemplate] = relationship("AgentTemplate", back_populates="agent_instances", lazy="joined")
    template_version: Mapped[TemplateVersion] = relationship("TemplateVersion", back_populates="agent_instances")
    current_session: Mapped[Optional["Session"]] = relationship(
        "Session",
        foreign_keys=[current_session_id],
        post_update=True
    )
    sessions: Mapped[List["Session"]] = relationship(
        "Session",
        back_populates="instance",
        foreign_keys="Session.instance_id"
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=False)
    uri: Mapped[str] = mapped_column(String(512), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    session: Mapped[Session] = relationship("Session", back_populates="sources")
    artifacts: Mapped[List["Artifact"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sources.id"), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    source: Mapped[Optional[Source]] = relationship("Source", back_populates="artifacts")
    session: Mapped[Optional[Session]] = relationship("Session", back_populates="artifacts")


class SystemPrompt(Base):
    """System-wide prompt templates that can be overridden per-template.
    
    These are the default prompts used by agents when no template-specific
    prompts are configured. Administrators can edit these through the Admin UI.
    
    Prompt keys:
    - system: Main system prompt with agent instructions
    - initial_user: Template for wrapping user's first message
    - clarification: Template for user clarification responses
    """
    __tablename__ = "system_prompts"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "system", "initial_user", "clarification"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    placeholders: Mapped[list] = mapped_column(JSON, default=list)  # List of placeholder names like ["current_date", "available_tools"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


__all__ = [
    "AgentInstance",
    "AgentTemplate",
    "Artifact",
    "Base",
    "Session",
    "SessionMessage",
    "Source",
    "SystemPrompt",
    "TemplateVersion",
    "Tool",
    "ToolExecution",
]
