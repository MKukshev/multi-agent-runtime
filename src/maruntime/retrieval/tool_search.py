from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from maruntime.persistence import Tool
from maruntime.retrieval.embeddings import EmbeddingProvider
from maruntime.runtime.templates import ToolPolicy


@dataclass(slots=True)
class ToolSearchResult:
    """Structured result for tool search operations."""

    tools: list[Tool]
    used_cache: bool = False


class ToolSearchService:
    """Service for retrieving tools using pgvector-style similarity and policy filters."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedding_provider: EmbeddingProvider | None = None,
        default_top_k: int = 10,
    ) -> None:
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider or EmbeddingProvider()
        self._default_top_k = default_top_k
        self._cache: dict[str, dict[str, list[str]]] = {}

    async def search(
        self,
        *,
        session_id: str,
        query: str,
        policy: ToolPolicy | None = None,
        available_tools: Sequence[str] | None = None,
        required_tools: Sequence[str] | None = None,
        top_k: int | None = None,
    ) -> ToolSearchResult:
        """Search tools by semantic similarity with policy-based filtering.

        Results are cached per session and query to avoid redundant vector work.
        """

        policy = policy or ToolPolicy()
        top_limit = top_k or policy.max_tools_in_prompt or self._default_top_k
        cached = self._cache.get(session_id, {}).get(query)
        if cached is not None:
            tools = await self._load_tools_by_names(cached)
            return ToolSearchResult(tools=tools, used_cache=True)

        embedding = await self._embedding_provider.embed_text(query)
        async with self._session_factory() as session:
            tools = await self._fetch_active_tools(session, available_tools)
        scored = [
            (tool, embedding.similarity(tool.embedding or []))
            for tool in tools
            if tool.embedding is not None
        ]
        # Keep tools without embeddings but with policy requirements
        missing_embedding = [tool for tool in tools if tool.embedding is None]

        filtered = self._apply_policy_filters(
            [tool for tool, _ in scored] + missing_embedding,
            policy,
            required_tools,
        )

        scored_filtered = [(tool, embedding.similarity(tool.embedding or [])) for tool in filtered]
        scored_filtered.sort(key=lambda pair: pair[1], reverse=True)

        ordered_tools = self._include_required(
            [tool for tool, _ in scored_filtered],
            required_tools or policy.required_tools,
        )

        limited = ordered_tools[:top_limit] if top_limit else ordered_tools
        self._cache.setdefault(session_id, {})[query] = [tool.name for tool in limited]
        return ToolSearchResult(tools=limited, used_cache=False)

    async def _fetch_active_tools(
        self,
        session: AsyncSession,
        available_tools: Sequence[str] | None,
    ) -> list[Tool]:
        stmt = select(Tool).where(Tool.is_active.is_(True))
        if available_tools:
            stmt = stmt.where(Tool.name.in_(available_tools))
        result = await session.scalars(stmt)
        return list(result.all())

    async def _load_tools_by_names(self, names: Sequence[str]) -> list[Tool]:
        if not names:
            return []
        async with self._session_factory() as session:
            result = await session.scalars(select(Tool).where(Tool.name.in_(names)))
            tools = list(result.all())
        ordered: list[Tool] = []
        lookup: Mapping[str, Tool] = {tool.name: tool for tool in tools}
        for name in names:
            tool = lookup.get(name)
            if tool:
                ordered.append(tool)
        return ordered

    @staticmethod
    def _apply_policy_filters(
        tools: Iterable[Tool],
        policy: ToolPolicy,
        required_tools: Sequence[str] | None,
    ) -> list[Tool]:
        required = set(required_tools or policy.required_tools or [])
        allowlist = set(policy.allowlist or [])
        denylist = set(policy.denylist or [])

        filtered: list[Tool] = []
        for tool in tools:
            if allowlist and tool.name not in allowlist and tool.name not in required:
                continue
            if tool.name in denylist:
                continue
            filtered.append(tool)
        return filtered

    @staticmethod
    def _include_required(tools: list[Tool], required_tools: Sequence[str] | None) -> list[Tool]:
        if not required_tools:
            return tools
        required_names = list(dict.fromkeys(required_tools))
        existing = {tool.name for tool in tools}
        ordered: list[Tool] = []
        for name in required_names:
            if name in existing:
                tool = next(tool for tool in tools if tool.name == name)
                ordered.append(tool)
        ordered.extend([tool for tool in tools if tool.name not in required_names])
        return ordered
