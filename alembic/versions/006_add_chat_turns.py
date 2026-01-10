"""Add chat_turns table for chat memory search.

Revision ID: 006_add_chat_turns
Revises: 005_add_message_type
Create Date: 2026-01-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "006_add_chat_turns"
down_revision: Union[str, None] = "005_add_message_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_postgres() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "chat_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "chat_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("assistant_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "search_text",
            sa.Text(),
            sa.Computed(
                "coalesce(user_text,'') || E'\\n\\n' || coalesce(assistant_text,'')",
                persisted=True,
            ),
        ),
        sa.Column(
            "search_text_norm",
            sa.Text(),
            sa.Computed(
                "lower(regexp_replace(coalesce(user_text,'') || E'\\n\\n' || coalesce(assistant_text,''), "
                "'[^[:alnum:][:space:]]+', ' ', 'g'))",
                persisted=True,
            ),
        ),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('russian', coalesce(user_text,'') || E'\\n\\n' || coalesce(assistant_text,''))",
                persisted=True,
            ),
        ),
        sa.UniqueConstraint("user_id", "chat_id", "turn_index", name="uq_chat_turns_order"),
    )

    op.create_index(
        "ix_chat_turns_owner_chat_pos",
        "chat_turns",
        ["user_id", "chat_id", "turn_index"],
    )
    op.create_index(
        "gin_chat_turns_search_tsv",
        "chat_turns",
        ["search_tsv"],
        postgresql_using="GIN",
    )
    op.create_index(
        "gin_chat_turns_search_trgm",
        "chat_turns",
        ["search_text_norm"],
        postgresql_using="GIN",
        postgresql_ops={"search_text_norm": "gin_trgm_ops"},
    )


def _create_generic() -> None:
    op.create_table(
        "chat_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("assistant_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=True),
        sa.Column("search_text_norm", sa.Text(), nullable=True),
        sa.Column("search_tsv", sa.Text(), nullable=True),
        sa.UniqueConstraint("user_id", "chat_id", "turn_index", name="uq_chat_turns_order"),
    )

    op.create_index(
        "ix_chat_turns_owner_chat_pos",
        "chat_turns",
        ["user_id", "chat_id", "turn_index"],
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _create_postgres()
    else:
        _create_generic()


def downgrade() -> None:
    op.drop_index("ix_chat_turns_owner_chat_pos", table_name="chat_turns")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("gin_chat_turns_search_trgm", table_name="chat_turns")
        op.drop_index("gin_chat_turns_search_tsv", table_name="chat_turns")
    op.drop_table("chat_turns")
