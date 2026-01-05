"""Web search tool using Tavily API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import Field

from maruntime.core.models import SearchResult
from maruntime.core.services.tavily_search import TavilySearchService
from maruntime.core.tools.base_tool import PydanticTool

if TYPE_CHECKING:
    from maruntime.core.models import AgentContext

logger = logging.getLogger(__name__)


class WebSearchTool(PydanticTool):
    """Search the web for real-time information about any topic.
    Use this tool when you need up-to-date information that might not be available in your training data,
    or when you need to verify current facts.
    The search results will include relevant snippets and URLs from web pages.
    This is particularly useful for questions about current events, technology updates,
    or any topic that requires recent information.
    Use for: Public information, news, market trends, external APIs, general knowledge
    Returns: Page titles, URLs, and short snippets (100 characters)
    Best for: Quick overview, finding relevant pages

    Usage:
        - Use SPECIFIC terms and context in queries
        - For acronyms, add context: "SGR Schema-Guided Reasoning"
        - Use quotes for exact phrases: "Structured Output OpenAI"
        - Search queries in SAME LANGUAGE as user request
        - For date/number questions, include specific year/context in query
        - Use ExtractPageContentTool to get full content from found URLs

    IMPORTANT FOR FACTUAL QUESTIONS:
        - Search snippets often contain direct answers - check them carefully
        - For questions with specific dates/numbers, snippets may be more accurate than full pages
        - If the snippet directly answers the question, you may not need to extract the full page
    """

    reasoning: str = Field(description="Why this search is needed and what to expect")
    query: str = Field(description="Search query in same language as user request")
    max_results: int = Field(
        description="Maximum results. How much of the web results selection you want to retrieve",
        default=5,
        ge=1,
        le=10,
    )

    async def __call__(
        self,
        context: AgentContext,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute web search using TavilySearchService."""
        logger.info(f"🔍 Search query: '{self.query}'")

        # Create search service from tool config
        search_service = TavilySearchService(config)
        max_results = min(self.max_results, config.get("max_results", 10) if config else 10)

        sources = await search_service.search(
            query=self.query,
            max_results=max_results,
            include_raw_content=False,
        )

        # Renumber sources starting from current count
        sources = TavilySearchService.rearrange_sources(
            sources, starting_number=len(context.sources) + 1
        )

        # Add sources to context
        for source in sources:
            context.sources[source.url] = source

        # Record search result
        search_result = SearchResult(
            query=self.query,
            answer=None,
            citations=sources,
            timestamp=datetime.now(),
        )
        context.searches.append(search_result)

        # Format results
        formatted_result = f"Search Query: {search_result.query}\n\n"
        formatted_result += "Search Results (titles, links, short snippets):\n\n"

        for source in sources:
            snippet = source.snippet[:100] + "..." if len(source.snippet) > 100 else source.snippet
            formatted_result += f"{str(source)}\n{snippet}\n\n"

        context.searches_used += 1
        logger.debug(formatted_result)
        return formatted_result


__all__ = ["WebSearchTool"]

