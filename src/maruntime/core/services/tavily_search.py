"""Tavily Search Service for web search and content extraction."""

from __future__ import annotations

import logging
import os
from typing import Any

from tavily import AsyncTavilyClient

from maruntime.core.models import SourceData

logger = logging.getLogger(__name__)


class TavilySearchConfig:
    """Configuration for Tavily Search Service."""

    def __init__(
        self,
        api_key: str | None = None,
        api_key_ref: str = "TAVILY_API_KEY",
        api_base_url: str | None = None,
        max_results: int = 5,
        content_limit: int = 5000,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv(api_key_ref, "")
        self.api_base_url = api_base_url
        self.max_results = max_results
        self.content_limit = content_limit
        self.timeout = timeout

    @classmethod
    def from_tool_config(cls, config: dict[str, Any] | None) -> TavilySearchConfig:
        """Create config from tool config dictionary."""
        if not config:
            return cls()

        # Resolve api_key_ref to actual key
        api_key = config.get("api_key")
        if not api_key and "api_key_ref" in config:
            api_key = os.getenv(config["api_key_ref"], "")

        return cls(
            api_key=api_key,
            api_base_url=config.get("api_base_url"),
            max_results=config.get("max_results", 5),
            content_limit=config.get("content_limit", 5000),
            timeout=config.get("timeout", 30),
        )


class TavilySearchService:
    """Service for web search and content extraction via Tavily API."""

    def __init__(self, config: TavilySearchConfig | dict[str, Any] | None = None) -> None:
        if isinstance(config, dict) or config is None:
            config = TavilySearchConfig.from_tool_config(config)

        self._config = config
        self._client = AsyncTavilyClient(
            api_key=config.api_key,
            api_base_url=config.api_base_url,
        )

    @staticmethod
    def rearrange_sources(sources: list[SourceData], starting_number: int = 1) -> list[SourceData]:
        """Renumber sources starting from given number."""
        for i, source in enumerate(sources, starting_number):
            source.number = i
        return sources

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        include_raw_content: bool = True,
    ) -> list[SourceData]:
        """Perform search through Tavily API and return results.

        Args:
            query: Search query
            max_results: Maximum number of results (default from config)
            include_raw_content: Include raw page content

        Returns:
            List of SourceData with search results
        """
        max_results = max_results or self._config.max_results
        logger.info(f"🔍 Tavily search: '{query}' (max_results={max_results})")

        response = await self._client.search(
            query=query,
            max_results=max_results,
            include_raw_content=include_raw_content,
        )

        return self._convert_to_source_data(response)

    async def extract(self, urls: list[str]) -> list[SourceData]:
        """Extract full content from specific URLs using Tavily Extract API.

        Args:
            urls: List of URLs to extract content from

        Returns:
            List of SourceData with extracted content
        """
        logger.info(f"📄 Tavily extract: {len(urls)} URLs")

        response = await self._client.extract(urls=urls)

        sources = []
        for i, result in enumerate(response.get("results", [])):
            if not result.get("url"):
                continue

            source = SourceData(
                number=i,
                title=result.get("url", "").split("/")[-1] or "Extracted Content",
                url=result.get("url", ""),
                snippet="",
                full_content=result.get("raw_content", ""),
                char_count=len(result.get("raw_content", "")),
            )
            sources.append(source)

        failed_urls = response.get("failed_results", [])
        if failed_urls:
            logger.warning(f"⚠️ Failed to extract {len(failed_urls)} URLs: {failed_urls}")

        return sources

    def _convert_to_source_data(self, response: dict[str, Any]) -> list[SourceData]:
        """Convert Tavily response to SourceData list."""
        sources = []

        for i, result in enumerate(response.get("results", [])):
            if not result.get("url", ""):
                continue

            source = SourceData(
                number=i,
                title=result.get("title", ""),
                url=result.get("url", ""),
                snippet=result.get("content", ""),
            )
            if result.get("raw_content", ""):
                source.full_content = result["raw_content"]
                source.char_count = len(source.full_content)
            sources.append(source)

        return sources


__all__ = ["TavilySearchService", "TavilySearchConfig"]

