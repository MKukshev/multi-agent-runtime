from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from maruntime.persistence import AgentTemplate, TemplateVersion
from maruntime.retrieval.embeddings import EmbeddingProvider


@dataclass(slots=True)
class AgentDirectoryEntry:
    """Result entry for agent directory search operations."""

    template: AgentTemplate
    version: TemplateVersion
    score: float


class AgentDirectoryService:
    """Retrieval service for agent templates based on embeddings."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedding_provider: EmbeddingProvider | None = None,
        default_top_k: int = 3,
    ) -> None:
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider or EmbeddingProvider()
        self._default_top_k = default_top_k

    async def index_template_version(self, template_version_id: str, *, text: str) -> TemplateVersion:
        """Compute and persist embedding for a template version."""

        embedding = await self._embedding_provider.embed_text(text)
        async with self._session_factory() as session:
            version = await session.get(TemplateVersion, template_version_id)
            if version is None:
                msg = f"TemplateVersion {template_version_id} not found"
                raise ValueError(msg)
            version.embedding = embedding.vector
            await session.commit()
            await session.refresh(version)
            return version

    async def bulk_index(self, versions: Sequence[tuple[str, str]]) -> list[TemplateVersion]:
        """Index multiple template versions at once."""

        indexed: list[TemplateVersion] = []
        for version_id, text in versions:
            indexed.append(await self.index_template_version(version_id, text=text))
        return indexed

    async def search(self, query: str, *, top_k: int | None = None, only_active: bool = True) -> list[AgentDirectoryEntry]:
        """Search templates by semantic similarity."""

        embedding = await self._embedding_provider.embed_text(query)
        versions = await self._load_candidates(only_active=only_active)
        scored: list[AgentDirectoryEntry] = [
            AgentDirectoryEntry(template=version.template, version=version, score=embedding.similarity(version.embedding or []))
            for version in versions
        ]
        scored.sort(key=lambda entry: entry.score, reverse=True)
        limit = top_k or self._default_top_k
        return scored[:limit] if limit else scored

    async def _load_candidates(self, *, only_active: bool) -> Iterable[TemplateVersion]:
        async with self._session_factory() as session:
            stmt = select(TemplateVersion).options(selectinload(TemplateVersion.template))
            if only_active:
                stmt = stmt.where(TemplateVersion.is_active.is_(True))
            stmt = stmt.where(TemplateVersion.embedding.is_not(None))
            result = await session.scalars(stmt)
            return list(result.all())


__all__ = ["AgentDirectoryEntry", "AgentDirectoryService"]
