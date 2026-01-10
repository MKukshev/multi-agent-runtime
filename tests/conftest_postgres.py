"""PostgreSQL-specific test configuration.

This module provides fixtures for testing with PostgreSQL instead of SQLite.
Use when running tests that require full PostgreSQL features (FTS, trigram, etc.).

Usage:
    # Run tests with PostgreSQL
    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/test_db \
        pytest tests/test_chat_memory_service.py -v

    # Or use the docker-compose test service
    docker compose -f docker-compose.test.yml up -d postgres-test
    TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test_maruntime \
        pytest tests/test_chat_memory_service.py -v
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Check if PostgreSQL URL is provided
POSTGRES_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def postgres_url() -> str | None:
    """Get PostgreSQL test URL from environment."""
    return POSTGRES_URL


@pytest.fixture
async def pg_session_factory():
    """Create async session factory for PostgreSQL tests."""
    if not POSTGRES_URL:
        pytest.skip("TEST_DATABASE_URL not set - skipping PostgreSQL tests")
    
    engine = create_async_engine(POSTGRES_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    
    yield factory
    
    await engine.dispose()


@pytest.fixture
async def pg_test_user(pg_session_factory) -> str:
    """Create a test user and return user_id."""
    from maruntime.persistence.models import User
    
    user_id = str(uuid.uuid4())
    async with pg_session_factory() as session:
        user = User(
            id=user_id,
            login=f"test_{user_id[:8]}@test.com",
            password_hash="$2b$12$test",
            display_name="Test User",
        )
        session.add(user)
        await session.commit()
    
    return user_id


@pytest.fixture
async def pg_test_session(pg_session_factory, pg_test_user) -> tuple[str, str]:
    """Create a test session and return (user_id, session_id)."""
    from maruntime.persistence.models import Session
    from maruntime.persistence import TemplateRepository
    
    session_id = str(uuid.uuid4())
    
    async with pg_session_factory() as session:
        # Get or create template
        repo = TemplateRepository(session)
        templates = await repo.list_templates()
        
        if templates:
            template = templates[0]
            version = await repo.get_latest_version(template.id)
            version_id = version.id if version else None
        else:
            template = await repo.create_template(name="test-agent", description="Test")
            version = await repo.create_version(template.id, settings={}, prompt="test")
            version_id = version.id
        
        if not version_id:
            pytest.skip("No template version available")
        
        chat_session = Session(
            id=session_id,
            template_version_id=version_id,
            user_id=pg_test_user,
            title="Test Chat",
            state="ACTIVE",
            context={},
        )
        session.add(chat_session)
        await session.commit()
    
    return pg_test_user, session_id
