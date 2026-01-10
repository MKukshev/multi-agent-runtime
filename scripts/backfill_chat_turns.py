#!/usr/bin/env python3
"""Backfill chat_turns table from memory_dir markdown files.

This script reads existing chat history from markdown files in memory_dir/chats/
and populates the chat_turns table in the database for FTS search.

Usage:
    # With default settings (reads from .env)
    python -m scripts.backfill_chat_turns

    # With explicit database URL
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db python -m scripts.backfill_chat_turns

    # Dry run (don't write to DB, just show what would be imported)
    python -m scripts.backfill_chat_turns --dry-run

    # Limit to specific user
    python -m scripts.backfill_chat_turns --user-id c8ffbd43-63d9-4b35-a2ba-19c714501eaa
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from maruntime.persistence.models import ChatTurn, Session, User


# Message header pattern (matches new format with [role])
MESSAGE_HEADER_RE = re.compile(
    r"^###\s+(?:\[(?P<role>[^\]]+)\]\s+)?(?P<actor>.+?)\s*\((?P<timestamp>[^)]+)\)\s*$"
)

# Legacy header pattern (without [role])
LEGACY_HEADER_RE = re.compile(
    r"^###\s+(?P<actor>.+?)\s*\((?P<timestamp>[^)]+)\)\s*$"
)


def parse_chat_file(file_path: Path) -> list[dict]:
    """Parse a chat markdown file into messages."""
    content = file_path.read_text(encoding="utf-8")
    messages = []
    current = None
    buffer = []
    
    for line in content.splitlines():
        # Try new format first
        header_match = MESSAGE_HEADER_RE.match(line)
        if not header_match:
            # Try legacy format
            header_match = LEGACY_HEADER_RE.match(line)
        
        if header_match:
            # Save previous message
            if current is not None:
                current["content"] = "\n".join(buffer).strip()
                messages.append(current)
                buffer = []
            
            # Parse role from header
            role = header_match.groupdict().get("role", "").strip().lower() if "role" in header_match.groupdict() else None
            actor = header_match.group("actor").strip()
            timestamp = header_match.group("timestamp").strip()
            
            # Infer role from actor name if not explicit
            if not role:
                actor_lower = actor.lower()
                if "agent" in actor_lower or "assistant" in actor_lower:
                    role = "assistant"
                else:
                    role = "user"
            
            current = {
                "role": role,
                "actor": actor,
                "timestamp": timestamp,
            }
            continue
        
        if line.strip() == "---":
            if current is not None:
                current["content"] = "\n".join(buffer).strip()
                messages.append(current)
                current = None
                buffer = []
            continue
        
        if current is not None:
            buffer.append(line)
    
    # Don't forget last message
    if current is not None:
        current["content"] = "\n".join(buffer).strip()
        messages.append(current)
    
    return messages


def build_turns(messages: list[dict]) -> list[dict]:
    """Group messages into Q/A turns."""
    turns = []
    current_turn = {"user": None, "assistant": None}
    
    for msg in messages:
        role = msg.get("role", "").lower()
        
        # Normalize role names
        if role in {"agent", "ai", "model", "bot"}:
            role = "assistant"
        elif role not in {"user", "assistant"}:
            # Guess from context
            if current_turn["user"] is None:
                role = "user"
            else:
                role = "assistant"
        
        if role == "user":
            # Start new turn if we already have a user message
            if current_turn["user"] is not None:
                turns.append(current_turn)
                current_turn = {"user": None, "assistant": None}
            current_turn["user"] = msg
        else:
            # Append to assistant (may have multiple assistant messages)
            if current_turn["assistant"] is None:
                current_turn["assistant"] = msg
            else:
                # Merge content
                existing = current_turn["assistant"].get("content", "")
                addition = msg.get("content", "")
                if addition:
                    current_turn["assistant"]["content"] = f"{existing}\n\n{addition}".strip()
    
    # Don't forget last turn
    if current_turn["user"] or current_turn["assistant"]:
        turns.append(current_turn)
    
    return turns


async def backfill_user_chats(
    session_factory: async_sessionmaker,
    user_id: str,
    chats_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Backfill chat_turns for a single user."""
    stats = {
        "files_processed": 0,
        "turns_created": 0,
        "turns_skipped": 0,
        "errors": [],
    }
    
    user_dir = chats_dir / user_id
    if not user_dir.exists():
        stats["errors"].append(f"User directory not found: {user_dir}")
        return stats
    
    async with session_factory() as session:
        # Verify user exists in DB
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalars().first()
        if not user:
            stats["errors"].append(f"User not found in DB: {user_id}")
            return stats
        
        for chat_file in user_dir.glob("*.md"):
            session_id = chat_file.stem
            
            # Verify session exists in DB
            session_result = await session.execute(
                select(Session).where(Session.id == session_id)
            )
            db_session = session_result.scalars().first()
            if not db_session:
                print(f"  ⚠️  Session not in DB, skipping: {session_id}")
                stats["turns_skipped"] += 1
                continue
            
            try:
                messages = parse_chat_file(chat_file)
                turns = build_turns(messages)
                
                print(f"  📄 {chat_file.name}: {len(messages)} messages → {len(turns)} turns")
                
                for idx, turn in enumerate(turns):
                    user_msg = turn.get("user") or {}
                    assistant_msg = turn.get("assistant") or {}
                    
                    user_text = user_msg.get("content", "")
                    assistant_text = assistant_msg.get("content", "")
                    
                    if not user_text and not assistant_text:
                        continue
                    
                    # Check if turn already exists
                    existing = await session.execute(
                        select(ChatTurn).where(
                            ChatTurn.user_id == user_id,
                            ChatTurn.chat_id == session_id,
                            ChatTurn.turn_index == idx,
                        )
                    )
                    if existing.scalars().first():
                        stats["turns_skipped"] += 1
                        continue
                    
                    if not dry_run:
                        chat_turn = ChatTurn(
                            user_id=user_id,
                            chat_id=session_id,
                            turn_index=idx,
                            user_text=user_text,
                            assistant_text=assistant_text if assistant_text else None,
                        )
                        session.add(chat_turn)
                    
                    stats["turns_created"] += 1
                
                stats["files_processed"] += 1
                
            except Exception as e:
                stats["errors"].append(f"{chat_file.name}: {e}")
        
        if not dry_run:
            await session.commit()
    
    return stats


async def main():
    parser = argparse.ArgumentParser(description="Backfill chat_turns from memory_dir")
    parser.add_argument(
        "--memory-dir",
        default="memory_dir/chats",
        help="Path to memory_dir/chats directory",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Database URL (default: from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--user-id",
        help="Limit to specific user ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to DB, just show what would be imported",
    )
    args = parser.parse_args()
    
    if not args.database_url:
        print("❌ DATABASE_URL not set. Use --database-url or set env var.")
        print("   Example: DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/maruntime")
        sys.exit(1)
    
    chats_dir = Path(args.memory_dir)
    if not chats_dir.exists():
        print(f"❌ Chats directory not found: {chats_dir}")
        sys.exit(1)
    
    print(f"🔗 Connecting to: {args.database_url.split('@')[-1]}")
    print(f"📁 Reading from: {chats_dir}")
    if args.dry_run:
        print("🔍 DRY RUN - no changes will be made")
    print()
    
    engine = create_async_engine(args.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    # Find user directories
    if args.user_id:
        user_ids = [args.user_id]
    else:
        user_ids = [d.name for d in chats_dir.iterdir() if d.is_dir()]
    
    total_stats = {
        "users_processed": 0,
        "files_processed": 0,
        "turns_created": 0,
        "turns_skipped": 0,
        "errors": [],
    }
    
    for user_id in user_ids:
        print(f"👤 Processing user: {user_id}")
        stats = await backfill_user_chats(
            session_factory,
            user_id,
            chats_dir,
            dry_run=args.dry_run,
        )
        
        total_stats["users_processed"] += 1
        total_stats["files_processed"] += stats["files_processed"]
        total_stats["turns_created"] += stats["turns_created"]
        total_stats["turns_skipped"] += stats["turns_skipped"]
        total_stats["errors"].extend(stats["errors"])
        print()
    
    await engine.dispose()
    
    # Summary
    print("=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    print(f"  Users processed:  {total_stats['users_processed']}")
    print(f"  Files processed:  {total_stats['files_processed']}")
    print(f"  Turns created:    {total_stats['turns_created']}")
    print(f"  Turns skipped:    {total_stats['turns_skipped']}")
    
    if total_stats["errors"]:
        print(f"\n⚠️  Errors ({len(total_stats['errors'])}):")
        for err in total_stats["errors"][:10]:
            print(f"    - {err}")
        if len(total_stats["errors"]) > 10:
            print(f"    ... and {len(total_stats['errors']) - 10} more")
    
    if args.dry_run:
        print("\n🔍 DRY RUN complete. Run without --dry-run to apply changes.")
    else:
        print("\n✅ Backfill complete!")


if __name__ == "__main__":
    asyncio.run(main())
