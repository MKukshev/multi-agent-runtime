"""Extend agent_instances with Named Slots model.

Revision ID: 20260105_000002
Revises: 20260105_000001
Create Date: 2026-01-05 15:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260105_000002"
down_revision: Union[str, None] = "20260105_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add instance_id to sessions table
    op.add_column(
        "sessions",
        sa.Column("instance_id", sa.String(36), nullable=True)
    )

    # Make last_heartbeat nullable (was NOT NULL in original schema)
    op.alter_column(
        "agent_instances",
        "last_heartbeat",
        nullable=True
    )

    # Extend agent_instances table with new columns
    # Identity columns
    op.add_column(
        "agent_instances",
        sa.Column("name", sa.String(100), nullable=True)
    )
    op.add_column(
        "agent_instances",
        sa.Column("display_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "agent_instances",
        sa.Column("description", sa.Text(), nullable=True)
    )

    # Rename session_id to current_session_id
    op.alter_column(
        "agent_instances",
        "session_id",
        new_column_name="current_session_id"
    )

    # Configuration columns
    op.add_column(
        "agent_instances",
        sa.Column("is_enabled", sa.Boolean(), nullable=True, server_default="true")
    )
    op.add_column(
        "agent_instances",
        sa.Column("auto_start", sa.Boolean(), nullable=True, server_default="false")
    )
    op.add_column(
        "agent_instances",
        sa.Column("priority", sa.Integer(), nullable=True, server_default="0")
    )
    op.add_column(
        "agent_instances",
        sa.Column("config_overrides", sa.JSON(), nullable=True)
    )

    # Statistics columns
    op.add_column(
        "agent_instances",
        sa.Column("total_sessions", sa.Integer(), nullable=True, server_default="0")
    )
    op.add_column(
        "agent_instances",
        sa.Column("total_messages", sa.Integer(), nullable=True, server_default="0")
    )
    op.add_column(
        "agent_instances",
        sa.Column("total_tool_calls", sa.Integer(), nullable=True, server_default="0")
    )
    op.add_column(
        "agent_instances",
        sa.Column("error_count", sa.Integer(), nullable=True, server_default="0")
    )
    op.add_column(
        "agent_instances",
        sa.Column("last_error", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_instances",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Lifecycle columns
    op.add_column(
        "agent_instances",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "agent_instances",
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "agent_instances",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Update existing rows: generate name from id, set status to OFFLINE
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE agent_instances 
        SET name = 'instance-' || SUBSTRING(id, 1, 8),
            status = 'OFFLINE',
            is_enabled = true,
            auto_start = false,
            priority = 0,
            total_sessions = 0,
            total_messages = 0,
            total_tool_calls = 0,
            error_count = 0
        WHERE name IS NULL
    """))

    # Now make name NOT NULL and add unique constraint
    op.alter_column("agent_instances", "name", nullable=False)
    op.create_unique_constraint("uq_agent_instances_name", "agent_instances", ["name"])

    # Add foreign key for sessions.instance_id
    op.create_foreign_key(
        "fk_session_instance",
        "sessions",
        "agent_instances",
        ["instance_id"],
        ["id"]
    )


def downgrade() -> None:
    # Remove foreign key
    op.drop_constraint("fk_session_instance", "sessions", type_="foreignkey")

    # Remove instance_id from sessions
    op.drop_column("sessions", "instance_id")

    # Remove unique constraint
    op.drop_constraint("uq_agent_instances_name", "agent_instances", type_="unique")

    # Remove new columns from agent_instances
    op.drop_column("agent_instances", "updated_at")
    op.drop_column("agent_instances", "stopped_at")
    op.drop_column("agent_instances", "started_at")
    op.drop_column("agent_instances", "last_error_at")
    op.drop_column("agent_instances", "last_error")
    op.drop_column("agent_instances", "error_count")
    op.drop_column("agent_instances", "total_tool_calls")
    op.drop_column("agent_instances", "total_messages")
    op.drop_column("agent_instances", "total_sessions")
    op.drop_column("agent_instances", "config_overrides")
    op.drop_column("agent_instances", "priority")
    op.drop_column("agent_instances", "auto_start")
    op.drop_column("agent_instances", "is_enabled")
    op.drop_column("agent_instances", "description")
    op.drop_column("agent_instances", "display_name")
    op.drop_column("agent_instances", "name")

    # Rename current_session_id back to session_id
    op.alter_column(
        "agent_instances",
        "current_session_id",
        new_column_name="session_id"
    )

