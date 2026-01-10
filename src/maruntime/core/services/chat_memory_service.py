"""Chat Memory Service - stores chat history in markdown files.

Each chat session is stored as a separate markdown file with:
- Session metadata (user, model, timestamps)
- Chronological message history (user -> assistant pairs)
- No reasoning steps, only final messages

When a database session factory is provided, the service also maintains a
chat_turns index for Postgres FTS/trigram search.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from maruntime.persistence.models import ChatTurn


logger = logging.getLogger(__name__)


class ChatMemoryService:
    """Service for persisting chat history to markdown files."""

    _MESSAGE_HEADER_RE = re.compile(
        r"^###\s+(?:\[(?P<role>[^\]]+)\]\s+)?(?P<actor>.+?)\s*\((?P<timestamp>[^)]+)\)\s*$"
    )
    _WORD_RE = re.compile(r"[A-Za-z0-9\u0400-\u04FF]+")
    _EN_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "he",
        "her",
        "his",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "she",
        "so",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }

    def __init__(
        self,
        base_dir: str = "memory_dir/chats",
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        fts_config: str = "russian",
        min_trgm_similarity: float = 0.25,
    ):
        """Initialize the chat memory service.
        
        Args:
            base_dir: Base directory for storing chat files.
            session_factory: Async SQLAlchemy session factory for DB-backed storage/search.
            fts_config: PostgreSQL FTS config name (e.g., "russian", "simple").
            min_trgm_similarity: Minimum trigram similarity threshold.
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._parsed_cache: dict[Path, tuple[float, list[dict]]] = {}
        self._session_factory = session_factory
        self._fts_config = fts_config
        self._min_trgm_similarity = min_trgm_similarity
        self._db_dialect: str | None = None

    def set_session_factory(self, session_factory: async_sessionmaker[AsyncSession] | None) -> None:
        self._session_factory = session_factory
        self._db_dialect = None

    def set_fts_config(self, fts_config: str) -> None:
        if fts_config:
            self._fts_config = fts_config

    def _get_user_dir(self, user_id: str) -> Path:
        """Get directory for user's chats."""
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_chat_file(self, user_id: str, session_id: str) -> Path:
        """Get file path for a specific chat session."""
        return self._get_user_dir(user_id) / f"{session_id}.md"

    async def save_message(
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

        role_label = role.lower() if role else "unknown"
        message_block = f"""
### [{role_label}] {actor} ({timestamp})

{content}

---
"""

        # Append message to file storage
        with open(chat_file, "a", encoding="utf-8") as f:
            f.write(message_block)
        self._parsed_cache.pop(chat_file, None)

        # Persist to database turn index if configured
        if self._session_factory:
            try:
                await self._save_message_db(
                    user_id=user_id,
                    session_id=session_id,
                    role=role,
                    content=content,
                )
            except SQLAlchemyError as exc:
                logger.warning("Chat memory DB write failed: %s", exc, exc_info=True)

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

    async def _get_db_dialect(self) -> str | None:
        if self._db_dialect is not None:
            return self._db_dialect
        if not self._session_factory:
            return None
        async with self._session_factory() as session:
            bind = session.get_bind()
            self._db_dialect = bind.dialect.name if bind is not None else None
        return self._db_dialect

    async def _next_turn_index(
        self, session: AsyncSession, user_id: str, session_id: str
    ) -> int:
        result = await session.execute(
            select(func.max(ChatTurn.turn_index)).where(
                ChatTurn.user_id == user_id,
                ChatTurn.chat_id == session_id,
            )
        )
        current = result.scalar()
        # Note: "current or -1" is wrong because 0 is falsy in Python
        return 0 if current is None else current + 1

    async def _save_message_db(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        if not self._session_factory:
            return

        role_lower = (role or "").lower()
        text_content = str(content or "")

        if role_lower == "user":
            # Each retry needs a fresh session to get accurate turn index
            for attempt in range(3):
                try:
                    async with self._session_factory() as session:
                        next_index = await self._next_turn_index(session, user_id, session_id)
                        turn = ChatTurn(
                            user_id=user_id,
                            chat_id=session_id,
                            turn_index=next_index,
                            user_text=text_content,
                            assistant_text=None,
                        )
                        session.add(turn)
                        await session.commit()
                        return
                except IntegrityError:
                    if attempt == 2:
                        raise
                    # Small delay before retry to allow concurrent writes to complete
                    import asyncio
                    await asyncio.sleep(0.01 * (attempt + 1))
        else:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(ChatTurn)
                    .where(
                        ChatTurn.user_id == user_id,
                        ChatTurn.chat_id == session_id,
                        ChatTurn.assistant_text.is_(None),
                    )
                    .order_by(ChatTurn.turn_index.desc())
                    .limit(1)
                )
                turn = result.scalars().first()
                if turn:
                    turn.assistant_text = text_content
                else:
                    next_index = await self._next_turn_index(session, user_id, session_id)
                    turn = ChatTurn(
                        user_id=user_id,
                        chat_id=session_id,
                        turn_index=next_index,
                        user_text="",
                        assistant_text=text_content,
                    )
                    session.add(turn)
                await session.commit()

    def _extract_title(self, content: str) -> str:
        first_line = content.split("\n", 1)[0].strip()
        if first_line.startswith("# Chat:"):
            title = first_line.replace("# Chat:", "", 1).strip()
            return title or "Unknown"
        return "Unknown"

    def _parse_messages(self, content: str) -> list[dict]:
        messages: list[dict] = []
        current: dict | None = None
        buffer: list[str] = []

        for line in content.splitlines():
            header_match = self._MESSAGE_HEADER_RE.match(line)
            if header_match:
                if current is not None:
                    current["content"] = "\n".join(buffer).strip()
                    messages.append(current)
                    buffer = []
                current = {
                    "role": (header_match.group("role") or "").strip().lower() or None,
                    "actor": header_match.group("actor").strip(),
                    "timestamp": header_match.group("timestamp").strip(),
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

        if current is not None:
            current["content"] = "\n".join(buffer).strip()
            messages.append(current)

        return messages

    def _build_turns(self, messages: list[dict]) -> list[dict]:
        turns: list[dict] = []
        current = {"user": None, "assistant": None}

        for message in messages:
            role = message.get("role")
            if role in {"agent", "ai", "model"}:
                role = "assistant"
            if role not in {"user", "assistant"}:
                if current["user"] is None:
                    role = "user"
                elif current["assistant"] is None:
                    role = "assistant"
                else:
                    turns.append(current)
                    current = {"user": None, "assistant": None}
                    role = "user"

            if role == "user":
                if current["user"] is not None:
                    turns.append(current)
                    current = {"user": None, "assistant": None}
                current["user"] = message
            else:
                if current["assistant"] is not None:
                    existing = current["assistant"].get("content", "")
                    addition = message.get("content", "")
                    if addition:
                        combined = f"{existing}\n\n{addition}".strip()
                        current["assistant"]["content"] = combined
                else:
                    current["assistant"] = message

        if current["user"] or current["assistant"]:
            turns.append(current)

        return turns

    def _stem_token(self, token: str) -> str:
        if not token.isascii():
            return token
        for suffix in ("ing", "edly", "ed", "es", "ly", "s"):
            if token.endswith(suffix) and len(token) > len(suffix) + 2:
                return token[: -len(suffix)]
        return token

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        tokens: list[str] = []
        for raw in self._WORD_RE.findall(text.lower()):
            if len(raw) < 2:
                continue
            if raw in self._EN_STOPWORDS:
                continue
            tokens.append(self._stem_token(raw))
        return tokens

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.strip().lower().split())

    def _trim_text(self, text: str, max_chars: int = 800) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    def _load_turns(self, chat_file: Path) -> list[dict]:
        try:
            stat = chat_file.stat()
        except FileNotFoundError:
            return []

        cached = self._parsed_cache.get(chat_file)
        if cached and cached[0] == stat.st_mtime:
            return cached[1]

        content = chat_file.read_text(encoding="utf-8")
        title = self._extract_title(content)
        messages = self._parse_messages(content)
        turns = self._build_turns(messages)

        for idx, turn in enumerate(turns):
            user_msg = turn.get("user") or {}
            assistant_msg = turn.get("assistant") or {}
            user_text = user_msg.get("content", "")
            assistant_text = assistant_msg.get("content", "")
            text_all = "\n".join([user_text, assistant_text]).strip()
            created_at = user_msg.get("timestamp") or assistant_msg.get("timestamp")

            tokens_user = self._tokenize(user_text)
            tokens_assistant = self._tokenize(assistant_text)
            tokens_all = self._tokenize(text_all)

            turn["session_id"] = chat_file.stem
            turn["turn_index"] = idx
            turn["title"] = title
            turn["created_at"] = created_at
            turn["text_all"] = text_all
            turn["tokens_user"] = tokens_user
            turn["tokens_assistant"] = tokens_assistant
            turn["tokens_all"] = tokens_all
            turn["token_set_all"] = set(tokens_all)
            turn["token_set_user"] = set(tokens_user)
            turn["token_set_assistant"] = set(tokens_assistant)
            turn["token_counts_user"] = Counter(tokens_user)
            turn["token_counts_assistant"] = Counter(tokens_assistant)
            turn["token_counts_all"] = Counter(tokens_all)

        self._parsed_cache[chat_file] = (stat.st_mtime, turns)
        return turns

    def _bm25_score(
        self,
        query_tokens: list[str],
        token_counts: Counter,
        doc_len: int,
        doc_freq: Counter,
        avgdl: float,
        n_docs: int,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        if not query_tokens or doc_len == 0 or avgdl == 0 or n_docs == 0:
            return 0.0
        score = 0.0
        for token in query_tokens:
            tf = token_counts.get(token, 0)
            if tf == 0:
                continue
            df = doc_freq.get(token, 0)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
            denom = tf + k1 * (1.0 - b + b * (doc_len / avgdl))
            score += idf * ((tf * (k1 + 1.0)) / denom)
        return score

    def _soft_match_count(self, query_tokens: list[str], text_lower: str) -> int:
        count = 0
        for token in query_tokens:
            if len(token) < 3:
                continue
            if token in text_lower:
                count += 1
        return count

    async def _search_chats_db(
        self,
        *,
        user_id: str,
        query: str,
        session_id: Optional[str],
        limit: int,
        per_session: int,
        min_score: float,
        context_turns: int,
    ) -> list[dict] | None:
        if not self._session_factory:
            return None

        dialect = await self._get_db_dialect()
        if dialect != "postgresql":
            return None

        query_text = (query or "").strip()
        if not query_text:
            return []

        hard_limit = max(limit * 4, limit)
        per_session = max(per_session, 1)
        context_turns = max(context_turns, 0)

        sql_candidates = text(
            """
            WITH params AS (
              SELECT
                websearch_to_tsquery(:cfg, :q) AS tsq,
                lower(:q) AS q_norm
            )
            SELECT
              t.id AS turn_id,
              t.chat_id AS session_id,
              t.turn_index,
              t.created_at,
              s.title AS session_title,
              (
                0.80 * ts_rank_cd(t.search_tsv, params.tsq)
                + 0.20 * similarity(t.search_text_norm, params.q_norm)
              ) AS score,
              ts_headline(
                :cfg,
                t.search_text,
                params.tsq,
                'MaxFragments=2,MinWords=6,MaxWords=28,StartSel=[H],StopSel=[/H]'
              ) AS headline
            FROM chat_turns t
            JOIN sessions s ON s.id = t.chat_id
            JOIN params ON true
            WHERE t.user_id = :user_id
              AND (:session_id IS NULL OR t.chat_id = :session_id)
              AND (
                t.search_tsv @@ params.tsq
                OR similarity(t.search_text_norm, params.q_norm) >= :min_sim
              )
            ORDER BY score DESC, t.created_at DESC
            LIMIT :hard_limit
            """
        )

        sql_window = text(
            """
            SELECT
              id,
              chat_id AS session_id,
              turn_index,
              created_at,
              user_text,
              assistant_text
            FROM chat_turns
            WHERE user_id = :user_id
              AND chat_id = :session_id
              AND turn_index BETWEEN :lo AND :hi
            ORDER BY turn_index ASC
            """
        )

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    sql_candidates,
                    {
                        "cfg": self._fts_config,
                        "q": query_text,
                        "user_id": user_id,
                        "session_id": session_id,
                        "min_sim": self._min_trgm_similarity,
                        "hard_limit": hard_limit,
                    },
                )
            ).mappings().all()

            hits: list[dict] = []
            for row in rows:
                score = float(row.get("score") or 0.0)
                if score < min_score:
                    continue
                hits.append(
                    {
                        "turn_id": row.get("turn_id"),
                        "session_id": row.get("session_id"),
                        "turn_index": int(row.get("turn_index") or 0),
                        "created_at": row.get("created_at"),
                        "session_title": row.get("session_title"),
                        "score": score,
                        "headline": row.get("headline") or "",
                    }
                )

            if not hits:
                return []

            selected: list[dict] = []
            per_session_counts: dict[str, int] = {}
            for hit in hits:
                session_key = hit.get("session_id") or ""
                count = per_session_counts.get(session_key, 0)
                if count >= per_session:
                    continue
                per_session_counts[session_key] = count + 1
                selected.append(hit)
                if len(selected) >= limit:
                    break

            results: list[dict] = []
            for hit in selected:
                lo = max(hit["turn_index"] - context_turns, 0)
                hi = hit["turn_index"] + context_turns

                window_rows = (
                    await session.execute(
                        sql_window,
                        {
                            "user_id": user_id,
                            "session_id": hit["session_id"],
                            "lo": lo,
                            "hi": hi,
                        },
                    )
                ).mappings().all()

                window_turns: list[dict] = []
                for wr in window_rows:
                    window_turns.append(
                        {
                            "turn_id": wr.get("id"),
                            "turn_index": int(wr.get("turn_index") or 0),
                            "created_at": wr.get("created_at").isoformat()
                            if wr.get("created_at")
                            else None,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": self._trim_text(wr.get("user_text") or ""),
                                },
                                {
                                    "role": "assistant",
                                    "content": self._trim_text(wr.get("assistant_text") or ""),
                                },
                            ],
                        }
                    )

                results.append(
                    {
                        "session_id": hit["session_id"],
                        "session_title": hit.get("session_title"),
                        "hit_turn_id": hit["turn_id"],
                        "hit_turn_index": hit["turn_index"],
                        "hit_created_at": hit["created_at"].isoformat()
                        if hit.get("created_at")
                        else None,
                        "score": round(hit["score"], 6),
                        "headline": hit.get("headline"),
                        "context_turns": window_turns,
                    }
                )

            return results

    def _search_chats_files(
        self,
        *,
        user_id: str,
        query: str,
        session_id: Optional[str],
        limit: int,
        per_session: int,
        min_score: float,
        context_turns: int,
    ) -> list[dict]:
        query_text = query.strip()
        if not query_text:
            return []

        user_dir = self._get_user_dir(user_id)

        if session_id:
            files = [self._get_chat_file(user_id, session_id)]
        else:
            files = list(user_dir.glob("*.md"))

        all_turns: list[dict] = []
        for chat_file in files:
            if not chat_file.exists():
                continue
            all_turns.extend(self._load_turns(chat_file))

        if not all_turns:
            return []

        turns_by_session: dict[str, list[dict]] = {}
        for turn in all_turns:
            session_key = turn.get("session_id") or ""
            turns_by_session.setdefault(session_key, []).append(turn)
        for turns in turns_by_session.values():
            turns.sort(key=lambda item: item.get("turn_index", 0))

        query_tokens = self._tokenize(query_text)
        normalized_query = self._normalize_query(query_text)

        doc_freq = Counter()
        total_len = 0
        for turn in all_turns:
            token_set = turn.get("token_set_all", set())
            doc_freq.update(token_set)
            total_len += len(turn.get("tokens_all", []))

        n_docs = len(all_turns)
        avgdl = total_len / n_docs if n_docs else 0.0

        common_tokens = {
            token
            for token, df in doc_freq.items()
            if n_docs and (df / n_docs) > 0.75 and len(token) <= 4
        }
        if query_tokens:
            filtered_query_tokens = [t for t in query_tokens if t not in common_tokens]
            if filtered_query_tokens:
                query_tokens = filtered_query_tokens

        query_set = set(query_tokens)
        scored: list[dict] = []

        if not query_tokens:
            query_lower = query_text.lower()
            for turn in all_turns:
                text_all = turn.get("text_all", "")
                if query_lower not in text_all.lower():
                    continue
                scored.append(
                    {
                        "session_id": turn.get("session_id"),
                        "session_title": turn.get("title"),
                        "turn_index": turn.get("turn_index", 0),
                        "created_at": turn.get("created_at"),
                        "score": 1.0,
                        "headline": self._trim_text(text_all, max_chars=240),
                        "matched_terms": [],
                    }
                )
        else:
            for turn in all_turns:
                text_all = turn.get("text_all", "")
                text_lower = text_all.lower()
                if not text_all:
                    continue

                overlap = len(query_set & turn.get("token_set_all", set()))
                soft_overlap = self._soft_match_count(query_tokens, text_lower)
                phrase_match = normalized_query and normalized_query in text_lower

                if overlap == 0 and soft_overlap == 0 and not phrase_match:
                    continue

                score_user = self._bm25_score(
                    query_tokens,
                    turn.get("token_counts_user", Counter()),
                    len(turn.get("tokens_user", [])),
                    doc_freq,
                    avgdl,
                    n_docs,
                )
                score_assistant = self._bm25_score(
                    query_tokens,
                    turn.get("token_counts_assistant", Counter()),
                    len(turn.get("tokens_assistant", [])),
                    doc_freq,
                    avgdl,
                    n_docs,
                )
                score_all = self._bm25_score(
                    query_tokens,
                    turn.get("token_counts_all", Counter()),
                    len(turn.get("tokens_all", [])),
                    doc_freq,
                    avgdl,
                    n_docs,
                )

                score = (score_user * 1.2) + (score_assistant * 1.0) + (score_all * 0.4)
                score += overlap * 0.3
                score += soft_overlap * 0.1
                if phrase_match:
                    score += 1.5
                if overlap == len(query_set) and overlap > 0:
                    score += 1.0

                if score < min_score:
                    continue

                scored.append(
                    {
                        "session_id": turn.get("session_id"),
                        "session_title": turn.get("title"),
                        "turn_index": turn.get("turn_index", 0),
                        "created_at": turn.get("created_at"),
                        "score": round(score, 4),
                        "headline": self._trim_text(text_all, max_chars=240),
                        "matched_terms": sorted(query_set & turn.get("token_set_all", set())),
                    }
                )

        if not scored:
            return []

        scored.sort(key=lambda item: item["score"], reverse=True)

        if per_session:
            limited_by_session: list[dict] = []
            per_session_counts: dict[str, int] = {}
            for item in scored:
                session_key = item.get("session_id") or ""
                count = per_session_counts.get(session_key, 0)
                if count >= per_session:
                    continue
                per_session_counts[session_key] = count + 1
                limited_by_session.append(item)
            scored = limited_by_session

        if limit:
            scored = scored[:limit]

        results: list[dict] = []
        context_turns = max(context_turns, 0)

        for hit in scored:
            session_key = hit.get("session_id") or ""
            turns = turns_by_session.get(session_key, [])
            hit_index = hit.get("turn_index", 0)
            lo = max(hit_index - context_turns, 0)
            hi = hit_index + context_turns

            window_turns: list[dict] = []
            for turn in turns:
                turn_index = turn.get("turn_index", 0)
                if turn_index < lo or turn_index > hi:
                    continue
                user_msg = turn.get("user") or {}
                assistant_msg = turn.get("assistant") or {}
                window_turns.append(
                    {
                        "turn_id": f"{session_key}:{turn_index}",
                        "turn_index": turn_index,
                        "created_at": turn.get("created_at"),
                        "messages": [
                            {
                                "role": "user",
                                "content": self._trim_text(user_msg.get("content", "")),
                            },
                            {
                                "role": "assistant",
                                "content": self._trim_text(assistant_msg.get("content", "")),
                            },
                        ],
                    }
                )

            results.append(
                {
                    "session_id": session_key,
                    "session_title": hit.get("session_title"),
                    "hit_turn_id": f"{session_key}:{hit.get('turn_index', 0)}",
                    "hit_turn_index": hit.get("turn_index", 0),
                    "hit_created_at": hit.get("created_at"),
                    "score": hit.get("score"),
                    "headline": hit.get("headline"),
                    "context_turns": window_turns,
                }
            )

        return results

    async def search_chats(
        self,
        user_id: str,
        query: str,
        *,
        session_id: Optional[str] = None,
        limit: int = 5,
        per_session: int = 2,
        min_score: float = 0.0,
        context_turns: int = 1,
    ) -> list[dict]:
        """Search chat history for a query."""
        if not query or not query.strip():
            return []

        if self._session_factory:
            try:
                db_results = await self._search_chats_db(
                    user_id=user_id,
                    query=query,
                    session_id=session_id,
                    limit=limit,
                    per_session=per_session,
                    min_score=min_score,
                    context_turns=context_turns,
                )
                if db_results is not None:
                    return db_results
            except SQLAlchemyError as exc:
                logger.warning("Chat memory DB search failed: %s", exc, exc_info=True)

        return self._search_chats_files(
            user_id=user_id,
            query=query,
            session_id=session_id,
            limit=limit,
            per_session=per_session,
            min_score=min_score,
            context_turns=context_turns,
        )


# Global instance
_chat_memory_service: Optional[ChatMemoryService] = None


def get_chat_memory_service(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    base_dir: str = "memory_dir/chats",
    fts_config: str = "russian",
) -> ChatMemoryService:
    """Get or create the global chat memory service."""
    global _chat_memory_service
    if _chat_memory_service is None:
        _chat_memory_service = ChatMemoryService(
            base_dir=base_dir,
            session_factory=session_factory,
            fts_config=fts_config,
        )
    else:
        if session_factory is not None:
            _chat_memory_service.set_session_factory(session_factory)
        if fts_config:
            _chat_memory_service.set_fts_config(fts_config)
    return _chat_memory_service
