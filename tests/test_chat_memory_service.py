"""Tests for ChatMemoryService.

These tests support both SQLite (limited) and PostgreSQL (full FTS).

Usage:
    # Run with SQLite (file fallback only, no DB search)
    pytest tests/test_chat_memory_service.py -v

    # Run with PostgreSQL (full FTS + trigram search)
    TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test_maruntime \
        pytest tests/test_chat_memory_service.py -v

    # Or use the test runner script
    ./scripts/run_tests_postgres.sh
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from maruntime.core.services.chat_memory_service import ChatMemoryService
from maruntime.persistence import TemplateRepository
from maruntime.persistence.models import ChatTurn, Session, User


# Check for PostgreSQL test URL
POSTGRES_URL = os.getenv("TEST_DATABASE_URL")


async def _setup_session(session_factory: async_sessionmaker) -> tuple[str, str]:
    """Create test user and session in database."""
    async with session_factory() as session:
        template_repo = TemplateRepository(session)
        template = await template_repo.create_template(name=f"chat-agent-{uuid.uuid4().hex[:8]}", description="test")
        version = await template_repo.create_version(template.id, settings={"temperature": 0.2}, prompt="hi")

        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            login=f"user_{user_id[:8]}@example.com",
            password_hash="hash",
            display_name="User",
        )
        session_id = str(uuid.uuid4())
        chat_session = Session(
            id=session_id,
            template_version_id=version.id,
            user_id=user_id,
            title="Test Chat",
            state="ACTIVE",
            context={},
        )
        session.add_all([user, chat_session])
        await session.commit()

    return user_id, session_id


@pytest.fixture
async def pg_engine():
    """Create PostgreSQL engine if TEST_DATABASE_URL is set."""
    if not POSTGRES_URL:
        pytest.skip("TEST_DATABASE_URL not set - run with PostgreSQL for full tests")
    
    engine = create_async_engine(POSTGRES_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_session_factory(pg_engine):
    """Create async session factory for PostgreSQL."""
    return async_sessionmaker(pg_engine, expire_on_commit=False)


# =============================================================================
# PostgreSQL Tests (require TEST_DATABASE_URL)
# =============================================================================

@pytest.mark.anyio
async def test_chat_memory_service_persists_turns_postgres(pg_session_factory, tmp_path: Path) -> None:
    """Test that turns are persisted to PostgreSQL database."""
    user_id, session_id = await _setup_session(pg_session_factory)
    chat_memory = ChatMemoryService(
        base_dir=str(tmp_path / "memory"),
        session_factory=pg_session_factory,
        fts_config="simple",  # Use simple config for tests
    )

    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="Hello",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="Hi there",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="Second question",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="Second answer",
    )

    async with pg_session_factory() as session:
        result = await session.execute(
            select(ChatTurn)
            .where(ChatTurn.user_id == user_id)
            .order_by(ChatTurn.turn_index)
        )
        turns = result.scalars().all()

    assert len(turns) == 2
    assert turns[0].turn_index == 0
    assert turns[0].user_text == "Hello"
    assert turns[0].assistant_text == "Hi there"
    assert turns[1].turn_index == 1
    assert turns[1].user_text == "Second question"
    assert turns[1].assistant_text == "Second answer"


@pytest.mark.anyio
async def test_chat_memory_service_search_postgres_fts(pg_session_factory, tmp_path: Path) -> None:
    """Test FTS search in PostgreSQL."""
    user_id, session_id = await _setup_session(pg_session_factory)
    chat_memory = ChatMemoryService(
        base_dir=str(tmp_path / "memory"),
        session_factory=pg_session_factory,
        fts_config="simple",
    )

    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="Tell me about Project Atlas",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="Project Atlas is the new internal initiative for data processing.",
    )

    results = await chat_memory.search_chats(
        user_id=user_id,
        query="Atlas",
        session_id=session_id,
        limit=3,
        context_turns=0,
    )

    assert results, "Should find results for 'Atlas'"
    hit = results[0]
    assert hit["session_id"] == session_id
    assert hit["context_turns"]
    user_message = hit["context_turns"][0]["messages"][0]["content"].lower()
    assert "atlas" in user_message


@pytest.mark.anyio
async def test_chat_memory_service_search_postgres_trigram(pg_session_factory, tmp_path: Path) -> None:
    """Test trigram similarity search in PostgreSQL."""
    user_id, session_id = await _setup_session(pg_session_factory)
    chat_memory = ChatMemoryService(
        base_dir=str(tmp_path / "memory"),
        session_factory=pg_session_factory,
        fts_config="simple",
        min_trgm_similarity=0.1,  # Lower threshold for testing
    )

    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="What is machine learning?",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="Machine learning is a subset of artificial intelligence.",
    )

    # Search with typo/partial match
    results = await chat_memory.search_chats(
        user_id=user_id,
        query="machin learn",  # Partial/typo query
        session_id=session_id,
        limit=3,
        context_turns=0,
    )

    assert results, "Should find results with trigram similarity"


# =============================================================================
# File-based Tests (work without database)
# =============================================================================

@pytest.mark.anyio
async def test_chat_memory_service_file_only(tmp_path: Path) -> None:
    """Test chat memory with file storage only (no database)."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    # No session_factory = file-only mode
    chat_memory = ChatMemoryService(base_dir=str(tmp_path / "memory"))

    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="Hello from file test",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="Hi there from file test",
    )

    # Check file was created
    chat_file = tmp_path / "memory" / user_id / f"{session_id}.md"
    assert chat_file.exists()
    content = chat_file.read_text()
    assert "Hello from file test" in content
    assert "Hi there from file test" in content


@pytest.mark.anyio
async def test_chat_memory_service_search_files(tmp_path: Path) -> None:
    """Test BM25 search on file storage."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    chat_memory = ChatMemoryService(base_dir=str(tmp_path / "memory"))

    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="Tell me about Project Atlas",
    )
    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="Project Atlas is the new internal initiative.",
    )

    results = await chat_memory.search_chats(
        user_id=user_id,
        query="Atlas",
        session_id=session_id,
        limit=3,
        context_turns=0,
    )

    assert results, "Should find results in file search"
    hit = results[0]
    assert hit["session_id"] == session_id
    assert hit["context_turns"]
    user_message = hit["context_turns"][0]["messages"][0]["content"].lower()
    assert "atlas" in user_message


@pytest.mark.anyio
async def test_chat_memory_service_list_chats(tmp_path: Path) -> None:
    """Test listing user chats."""
    user_id = str(uuid.uuid4())
    
    chat_memory = ChatMemoryService(base_dir=str(tmp_path / "memory"))

    # Create multiple chats
    for i in range(3):
        session_id = str(uuid.uuid4())
        await chat_memory.save_message(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=f"Chat {i} message",
            session_title=f"Chat {i}",
        )

    chats = chat_memory.list_user_chats(user_id)
    assert len(chats) == 3


@pytest.mark.anyio
async def test_chat_memory_service_delete_chat(tmp_path: Path) -> None:
    """Test deleting a chat."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    chat_memory = ChatMemoryService(base_dir=str(tmp_path / "memory"))

    await chat_memory.save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content="To be deleted",
    )

    # Verify exists
    assert chat_memory.get_chat_history(user_id, session_id)

    # Delete
    result = chat_memory.delete_chat(user_id, session_id)
    assert result is True

    # Verify deleted
    assert chat_memory.get_chat_history(user_id, session_id) == ""
