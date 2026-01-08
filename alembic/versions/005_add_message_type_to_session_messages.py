"""Add message_type and step_data to session_messages.

Revision ID: 005_add_message_type
Revises: 004_add_auth_tables
Create Date: 2026-01-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_add_message_type'
down_revision: Union[str, None] = '20260108_000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add message_type column with default 'message'
    op.add_column(
        'session_messages',
        sa.Column('message_type', sa.String(50), nullable=False, server_default='message')
    )
    
    # Add step_number column
    op.add_column(
        'session_messages',
        sa.Column('step_number', sa.Integer, nullable=True)
    )
    
    # Add step_data column for additional step metadata (tool_name, args, result, etc.)
    op.add_column(
        'session_messages',
        sa.Column('step_data', sa.JSON, nullable=True)
    )
    
    # Create index for faster queries by message_type
    op.create_index('ix_session_messages_message_type', 'session_messages', ['message_type'])


def downgrade() -> None:
    op.drop_index('ix_session_messages_message_type')
    op.drop_column('session_messages', 'step_data')
    op.drop_column('session_messages', 'step_number')
    op.drop_column('session_messages', 'message_type')
