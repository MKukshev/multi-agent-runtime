"""Core components for the multi-agent runtime."""

from maruntime.core.agents import BaseAgent, SimpleAgent
from maruntime.core.llm import LLMClientFactory
from maruntime.core.models import (
    AgentContext,
    AgentStatesEnum,
    SearchResult,
    SourceData,
    ToolConfig,
)
from maruntime.core.services import (
    AgentRegistry,
    PromptLoader,
    TavilySearchConfig,
    TavilySearchService,
    ToolRegistry,
)
from maruntime.core.streaming import OpenAIStreamingGenerator, SSEEvent
from maruntime.core.tools import (
    AdaptPlanTool,
    BaseTool,
    ClarificationTool,
    CreateReportTool,
    DelegateTemplateTool,
    EchoTool,
    ExtractPageContentTool,
    FinalAnswerTool,
    GeneratePlanTool,
    MCPBaseTool,
    PydanticTool,
    ReasoningTool,
    ToolConfigResolver,
    WebSearchTool,
)

__all__ = [
    # Agents
    "AgentRegistry",
    "BaseAgent",
    "SimpleAgent",
    # LLM
    "LLMClientFactory",
    # Models
    "AgentContext",
    "AgentStatesEnum",
    "SearchResult",
    "SourceData",
    "ToolConfig",
    # Services
    "PromptLoader",
    "TavilySearchConfig",
    "TavilySearchService",
    "ToolRegistry",
    # Streaming
    "OpenAIStreamingGenerator",
    "SSEEvent",
    # Tools - Base
    "BaseTool",
    "MCPBaseTool",
    "PydanticTool",
    "ToolConfigResolver",
    # Tools - SGR Research
    "AdaptPlanTool",
    "ClarificationTool",
    "CreateReportTool",
    "ExtractPageContentTool",
    "FinalAnswerTool",
    "GeneratePlanTool",
    "ReasoningTool",
    "WebSearchTool",
    # Tools - Utility
    "DelegateTemplateTool",
    "EchoTool",
]
