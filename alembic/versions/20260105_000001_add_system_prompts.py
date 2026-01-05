"""Add system_prompts table.

Revision ID: 20260105_000001
Revises: 20240708_000001
Create Date: 2026-01-05 00:00:01.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260105_000001"
down_revision: Union[str, None] = "20240708_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default prompts to seed
DEFAULT_PROMPTS = [
    {
        "id": "system",
        "name": "System Prompt",
        "description": "Main system prompt with agent instructions, capabilities, and guidelines",
        "content": """<MAIN_TASK_GUIDELINES>
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
""",
        "placeholders": ["current_date", "available_tools"],
    },
    {
        "id": "initial_user",
        "name": "Initial User Request",
        "description": "Template for wrapping user's first message with context",
        "content": """Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)

USER REQUEST:

{task}
""",
        "placeholders": ["current_date", "task"],
    },
    {
        "id": "clarification",
        "name": "Clarification Response",
        "description": "Template for formatting user's clarification responses",
        "content": """Current Date: {current_date} (Year-Month-Day ISO format: YYYY-MM-DD HH:MM:SS)

USER CLARIFICATION:

{clarifications}

Please continue with your task using this additional information.
""",
        "placeholders": ["current_date", "clarifications"],
    },
]


def upgrade() -> None:
    # Create system_prompts table
    op.create_table(
        "system_prompts",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("placeholders", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed default prompts
    bind = op.get_bind()
    meta = sa.MetaData()
    system_prompts = sa.Table(
        "system_prompts",
        meta,
        sa.Column("id", sa.String(50)),
        sa.Column("name", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("placeholders", sa.JSON),
        sa.Column("is_active", sa.Boolean),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    from datetime import datetime
    now = datetime.utcnow()

    for prompt in DEFAULT_PROMPTS:
        bind.execute(
            system_prompts.insert().values(
                id=prompt["id"],
                name=prompt["name"],
                description=prompt["description"],
                content=prompt["content"],
                placeholders=prompt["placeholders"],
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    op.drop_table("system_prompts")

