"""Lightweight embedding helpers and provider utilities."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


def _normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(l * r for l, r in zip(left, right))


@dataclass(slots=True)
class Embedding:
    """Container for an embedding vector with similarity utilities."""

    vector: list[float]

    @classmethod
    def from_iterable(cls, values: Iterable[float]) -> "Embedding":
        return cls(list(values))

    def similarity(self, other: Sequence[float]) -> float:
        return cosine_similarity(self.vector, other)


class EmbeddingProvider:
    """Simple, deterministic embedding provider.

    The default implementation hashes text into a fixed-size vector, avoiding
    external dependencies while remaining deterministic for caching and tests.
    """

    def __init__(self, *, model: str | None = None, embedder: Callable[[str], Sequence[float]] | None = None):
        self.model = model or "hash-embedding"
        self._embedder = embedder or self._default_embedder

    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        return [Embedding.from_iterable(_normalize(self._embedder(text))) for text in texts]

    async def embed_text(self, text: str) -> Embedding:
        (embedding,) = await self.embed([text])
        return embedding

    def _default_embedder(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[:64]]


__all__ = ["Embedding", "EmbeddingProvider", "cosine_similarity"]
