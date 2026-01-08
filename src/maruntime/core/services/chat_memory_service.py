"""Chat Memory Service - stores chat history in markdown files.

Each chat session is stored as a separate markdown file with:
- Session metadata (user, model, timestamps)
- Chronological message history (user -> assistant pairs)
- No reasoning steps, only final messages
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from maruntime.persistence.models import Session, SessionMessage


class ChatMemoryService:
    """Service for persisting chat history to markdown files."""

    def __init__(self, base_dir: str = "memory_dir/chats"):
        """Initialize the chat memory service.
        
        Args:
            base_dir: Base directory for storing chat files.
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_dir(self, user_id: str) -> Path:
        """Get directory for user's chats."""
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_chat_file(self, user_id: str, session_id: str) -> Path:
        """Get file path for a specific chat session."""
        return self._get_user_dir(user_id) / f"{session_id}.md"

    def save_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        *,
        user_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        model_name: Optional[str] = None,
        session_title: Optional[str] = None,
    ) -> None:
        """Append a message to the chat history file.
        
        Args:
            user_id: User ID
            session_id: Session/chat ID
            role: Message role (user/assistant)
            content: Message content
            user_name: Display name for user messages
            agent_name: Display name for assistant messages
            model_name: Model name (for header)
            session_title: Chat session title (for header)
        """
        chat_file = self._get_chat_file(user_id, session_id)
        
        # Create header if file doesn't exist
        if not chat_file.exists():
            self._write_header(chat_file, session_id, session_title, model_name)
        
        # Format message
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        actor = user_name if role == "user" else (agent_name or "Agent")
        
        message_block = f"""
### {actor} ({timestamp})

{content}

---
"""
        
        # Append message
        with open(chat_file, "a", encoding="utf-8") as f:
            f.write(message_block)

    def _write_header(
        self,
        chat_file: Path,
        session_id: str,
        title: Optional[str],
        model: Optional[str],
    ) -> None:
        """Write file header with metadata."""
        header = f"""# Chat: {title or 'New Chat'}

**Session ID:** `{session_id}`
**Model:** {model or 'Unknown'}
**Created:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

## Messages

"""
        with open(chat_file, "w", encoding="utf-8") as f:
            f.write(header)

    def get_chat_history(self, user_id: str, session_id: str) -> str:
        """Read chat history for a session.
        
        Returns:
            Markdown content of the chat, or empty string if not found.
        """
        chat_file = self._get_chat_file(user_id, session_id)
        if chat_file.exists():
            return chat_file.read_text(encoding="utf-8")
        return ""

    def list_user_chats(self, user_id: str) -> list[dict]:
        """List all chat files for a user.
        
        Returns:
            List of chat info dicts with id, title, modified time.
        """
        user_dir = self._get_user_dir(user_id)
        chats = []
        
        for chat_file in user_dir.glob("*.md"):
            # Extract title from first line
            try:
                with open(chat_file, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    title = first_line.replace("# Chat: ", "") if first_line.startswith("# Chat:") else "Unknown"
            except Exception:
                title = "Unknown"
            
            stat = chat_file.stat()
            chats.append({
                "id": chat_file.stem,
                "title": title,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        
        # Sort by modified time, newest first
        chats.sort(key=lambda x: x["modified"], reverse=True)
        return chats

    def delete_chat(self, user_id: str, session_id: str) -> bool:
        """Delete a chat history file.
        
        Returns:
            True if deleted, False if not found.
        """
        chat_file = self._get_chat_file(user_id, session_id)
        if chat_file.exists():
            chat_file.unlink()
            return True
        return False

    def search_chats(
        self,
        user_id: str,
        query: str,
        *,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """Search chat history for a query.
        
        Args:
            user_id: User ID
            query: Search query
            session_id: Optional specific session to search (None = all sessions)
            
        Returns:
            List of search results with session_id, title, and matching excerpts.
        """
        results = []
        user_dir = self._get_user_dir(user_id)
        query_lower = query.lower()
        
        # Determine files to search
        if session_id:
            files = [self._get_chat_file(user_id, session_id)]
        else:
            files = list(user_dir.glob("*.md"))
        
        for chat_file in files:
            if not chat_file.exists():
                continue
                
            content = chat_file.read_text(encoding="utf-8")
            if query_lower in content.lower():
                # Extract title
                first_line = content.split("\n")[0]
                title = first_line.replace("# Chat: ", "") if first_line.startswith("# Chat:") else "Unknown"
                
                # Find matching lines
                lines = content.split("\n")
                matches = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        # Get context (2 lines before and after)
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        excerpt = "\n".join(lines[start:end])
                        matches.append(excerpt)
                
                results.append({
                    "session_id": chat_file.stem,
                    "title": title,
                    "matches": matches[:5],  # Limit to 5 excerpts
                })
        
        return results


# Global instance
_chat_memory_service: Optional[ChatMemoryService] = None


def get_chat_memory_service() -> ChatMemoryService:
    """Get or create the global chat memory service."""
    global _chat_memory_service
    if _chat_memory_service is None:
        _chat_memory_service = ChatMemoryService()
    return _chat_memory_service
