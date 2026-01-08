"""Add authentication tables and user_id to sessions

Revision ID: 20260108_000001
Revises: 20260105_000002
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260108_000001'
down_revision = '20260105_000002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('login', sa.String(50), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('about', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create auth_sessions table
    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, index=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_auth_sessions_user', 'auth_sessions', ['user_id'])

    # Add user_id and title columns to sessions table
    op.add_column('sessions', sa.Column('user_id', sa.String(36), nullable=True))
    op.add_column('sessions', sa.Column('title', sa.String(255), server_default='New Chat'))
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_sessions_user',
        'sessions', 'users',
        ['user_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_sessions_user', 'sessions', ['user_id'])


def downgrade() -> None:
    # Remove index and foreign key from sessions
    op.drop_index('idx_sessions_user', table_name='sessions')
    op.drop_constraint('fk_sessions_user', 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'title')
    op.drop_column('sessions', 'user_id')

    # Drop auth_sessions table
    op.drop_index('idx_auth_sessions_user', table_name='auth_sessions')
    op.drop_table('auth_sessions')

    # Drop users table
    op.drop_table('users')
