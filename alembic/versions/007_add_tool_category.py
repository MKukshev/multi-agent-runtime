"""Add category column to tools.

Revision ID: 007_add_tool_category
Revises: 006_add_chat_turns
Create Date: 2026-01-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "007_add_tool_category"
down_revision: Union[str, None] = "006_add_chat_turns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column("category", sa.String(50), nullable=False, server_default="utility"),
    )


def downgrade() -> None:
    op.drop_column("tools", "category")
