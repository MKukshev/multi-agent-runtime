"""Template service for managing agent templates and runtime configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from maruntime.retrieval.embeddings import EmbeddingProvider
from maruntime.persistence import AgentTemplate, TemplateRepository, TemplateVersion

if TYPE_CHECKING:
    from maruntime.core.services.prompt_loader import PromptsConfig


class LLMPolicy(BaseModel):
    """LLM configuration for agent template."""

    base_url: Optional[str] = None
    api_key_ref: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    streaming: bool = False


class PromptConfig(BaseModel):
    """Prompt templates with placeholders.
    
    All fields are optional and will use default prompts if not specified.
    See maruntime.core.services.prompt_loader for default values.
    """

    system: Optional[str] = None
    initial_user: Optional[str] = None
    clarification: Optional[str] = None

    def to_prompts_config(self) -> "PromptsConfig":
        """Convert to PromptsConfig for use in agent execution.
        
        Applies defaults for any missing fields.
        """
        # Import here to avoid circular imports
        from maruntime.core.services.prompt_loader import (
            DEFAULT_CLARIFICATION_RESPONSE,
            DEFAULT_INITIAL_USER_REQUEST,
            DEFAULT_SYSTEM_PROMPT,
            PromptsConfig,
        )
        return PromptsConfig(
            system_prompt=self.system or DEFAULT_SYSTEM_PROMPT,
            initial_user_request=self.initial_user or DEFAULT_INITIAL_USER_REQUEST,
            clarification_response=self.clarification or DEFAULT_CLARIFICATION_RESPONSE,
        )


class ExecutionPolicy(BaseModel):
    """Global execution limits for agent session."""

    max_iterations: Optional[int] = Field(default=15, description="Max agent iterations")
    time_budget_seconds: Optional[int] = Field(default=None, description="Time limit for session")


class ToolQuota(BaseModel):
    """Per-tool execution limits and settings."""

    max_calls: Optional[int] = Field(default=None, description="Max calls per session (null=unlimited)")
    timeout: Optional[int] = Field(default=30, description="Timeout in seconds per call")
    cooldown_seconds: Optional[float] = Field(default=None, description="Delay between calls")


class ToolPolicy(BaseModel):
    """Tool access policy and per-tool quotas."""

    required_tools: list[str] = Field(default_factory=list, description="Tools that must be available")
    allowlist: list[str] = Field(default_factory=list, description="Allowed tools (empty=all)")
    denylist: list[str] = Field(default_factory=list, description="Denied tools")
    max_tools_in_prompt: Optional[int] = Field(default=None, description="Max tools to include in prompt")
    selection_strategy: Optional[str] = Field(default=None, description="Tool selection strategy")

    # Per-tool quotas (overrides tool.config.execution defaults)
    quotas: dict[str, ToolQuota] = Field(
        default_factory=dict,
        description="Per-tool limits: {tool_name: {max_calls, timeout, cooldown_seconds}}"
    )

    def get_quota(self, tool_name: str) -> ToolQuota:
        """Get quota for a tool, falling back to defaults."""
        if tool_name in self.quotas:
            return self.quotas[tool_name]
        # Return default quota
        return self.quotas.get("_default", ToolQuota())


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server.
    
    Supports two modes:
    - HTTP: Use `url` for HTTP-based MCP servers
    - Stdio: Use `command` and `args` for local MCP servers
    """
    
    # HTTP-based MCP server
    url: Optional[str] = Field(default=None, description="URL for HTTP-based MCP server")
    
    # Stdio-based MCP server
    command: Optional[str] = Field(default=None, description="Command to run (e.g., 'npx', 'python')")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    
    # Common settings
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    timeout: int = Field(default=30, description="Connection timeout in seconds")
    enabled: bool = Field(default=True, description="Whether this server is enabled")


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) configuration.
    
    Defines external MCP servers that provide additional tools and context
    to agents. Each server can be HTTP-based (url) or stdio-based (command).
    """
    
    mcpServers: dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="Named MCP server configurations"
    )
    context_limit: int = Field(
        default=20000,
        description="Max context size from MCP servers (tokens)"
    )
    enabled: bool = Field(default=True, description="Enable MCP integration")

    def get_enabled_servers(self) -> dict[str, MCPServerConfig]:
        """Get only enabled MCP servers."""
        return {
            name: config
            for name, config in self.mcpServers.items()
            if config.enabled
        }


class TemplateRuntimeConfig(BaseModel):
    """Complete runtime configuration for an agent template version."""

    template_id: str
    template_name: str
    version_id: str
    version: int

    # Agent class to instantiate
    base_class: str = Field(
        default="maruntime.core.agents.simple_agent:SimpleAgent",
        description="Python import path to agent class (module:ClassName)"
    )

    # Configuration sections
    llm_policy: LLMPolicy
    prompts: PromptConfig
    execution_policy: ExecutionPolicy
    tool_policy: ToolPolicy
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    # Tools assigned to this template version
    tools: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    rules: list[dict[str, Any]] = Field(default_factory=list)

    def get_tool_quota(self, tool_name: str) -> ToolQuota:
        """Get quota for a specific tool."""
        return self.tool_policy.get_quota(tool_name)

    def get_prompts_config(self) -> "PromptsConfig":
        """Get PromptsConfig for agent execution with defaults applied."""
        return self.prompts.to_prompts_config()


class TemplateService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, embedding_provider: EmbeddingProvider | None = None):
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider or EmbeddingProvider()

    async def create(self, name: str, description: Optional[str] = None) -> AgentTemplate:
        async with self._session_factory() as session:
            repo = TemplateRepository(session)
            template = await repo.create_template(name=name, description=description)
            await session.commit()
            return template

    async def create_version(
        self,
        template_id: str,
        *,
        base_class: Optional[str] = None,
        llm_policy: LLMPolicy | dict[str, Any],
        prompts: PromptConfig | dict[str, Any] | None = None,
        execution_policy: ExecutionPolicy | dict[str, Any] | None = None,
        tool_policy: ToolPolicy | dict[str, Any] | None = None,
        tools: Optional[Sequence[str]] = None,
        prompt: Optional[str] = None,
        version: Optional[int] = None,
        activate: bool = False,
        rules: Optional[Sequence[dict[str, Any]]] = None,
        embedding_text: Optional[str] = None,
    ) -> TemplateVersion:
        llm_policy_model = self._as_model(LLMPolicy, llm_policy)
        prompts_model = self._as_model(PromptConfig, prompts) if prompts is not None else PromptConfig()
        execution_policy_model = (
            self._as_model(ExecutionPolicy, execution_policy) if execution_policy is not None else ExecutionPolicy()
        )
        tool_policy_model = self._as_model(ToolPolicy, tool_policy) if tool_policy is not None else ToolPolicy()
        embedding_vector = None
        if embedding_text:
            embedding_vector = (await self._embedding_provider.embed_text(embedding_text)).vector

        settings = {
            "base_class": base_class or "maruntime.core.agents.simple_agent:SimpleAgent",
            "llm_policy": llm_policy_model.model_dump(),
            "prompts": prompts_model.model_dump(),
            "execution_policy": execution_policy_model.model_dump(),
            "tool_policy": tool_policy_model.model_dump(),
            "rules": list(rules or []),
        }

        async with self._session_factory() as session:
            repo = TemplateRepository(session)
            template_version = await repo.create_version(
                template_id,
                version=version,
                settings=settings,
                embedding=embedding_vector,
                prompt=prompt or prompts_model.system,
                tools=list(tools) if tools is not None else [],
                is_active=activate,
            )
            await session.commit()
            return template_version

    async def activate(self, template_id: str, version_id: str) -> Optional[TemplateRuntimeConfig]:
        async with self._session_factory() as session:
            repo = TemplateRepository(session)
            version = await repo.activate_version(template_id, version_id)
            if version is None:
                return None
            await session.commit()
            template = await repo.get_template(template_id)
            return self._build_runtime_config(template, version) if template else None

    async def get_active(self, template_id: str) -> Optional[TemplateRuntimeConfig]:
        async with self._session_factory() as session:
            repo = TemplateRepository(session)
            template = await repo.get_template(template_id)
            if template is None or template.active_version_id is None:
                return None
            version = await session.get(TemplateVersion, template.active_version_id)
            return self._build_runtime_config(template, version) if version else None

    async def get_runtime_config_for_version(self, version_id: str) -> Optional[TemplateRuntimeConfig]:
        async with self._session_factory() as session:
            version = await self._get_version_with_template(session, version_id)
            if version is None:
                return None
            template = version.template
            return self._build_runtime_config(template, version) if template else None

    async def list_active_models(self) -> list[TemplateRuntimeConfig]:
        async with self._session_factory() as session:
            repo = TemplateRepository(session)
            templates = await repo.list_templates()
            active_configs: list[TemplateRuntimeConfig] = []
            for template in templates:
                if template.active_version_id is None:
                    continue
                version = await self._get_version_with_template(session, template.active_version_id)
                if version is None:
                    continue
                active_configs.append(self._build_runtime_config(template, version))
            return active_configs

    async def get_version_with_template(self, version_id: str) -> TemplateVersion | None:
        async with self._session_factory() as session:
            return await self._get_version_with_template(session, version_id)

    @staticmethod
    def _as_model(model_cls: type[BaseModel], value: BaseModel | dict[str, Any]) -> BaseModel:
        if isinstance(value, model_cls):
            return value
        if isinstance(value, dict):
            return model_cls(**value)
        msg = f"Unsupported value for {model_cls.__name__}: {type(value)}"
        raise TypeError(msg)

    @staticmethod
    def _build_runtime_config(template: AgentTemplate, version: TemplateVersion) -> TemplateRuntimeConfig:
        settings = version.settings or {}

        # Parse base_class with fallback
        base_class = settings.get("base_class", "maruntime.core.agents.simple_agent:SimpleAgent")

        # Parse policy sections
        llm_policy = LLMPolicy(**settings.get("llm_policy", {}))
        prompts = PromptConfig(**settings.get("prompts", {}))
        execution_policy = ExecutionPolicy(**settings.get("execution_policy", {}))

        # Parse tool_policy with quotas
        tool_policy_data = settings.get("tool_policy", {})
        # Convert quotas dict to ToolQuota objects
        if "quotas" in tool_policy_data and isinstance(tool_policy_data["quotas"], dict):
            tool_policy_data = tool_policy_data.copy()
            tool_policy_data["quotas"] = {
                name: ToolQuota(**quota) if isinstance(quota, dict) else quota
                for name, quota in tool_policy_data["quotas"].items()
            }
        tool_policy = ToolPolicy(**tool_policy_data)

        # Parse MCP config
        mcp_data = settings.get("mcp", {})
        if "mcpServers" in mcp_data and isinstance(mcp_data["mcpServers"], dict):
            mcp_data = mcp_data.copy()
            mcp_data["mcpServers"] = {
                name: MCPServerConfig(**server) if isinstance(server, dict) else server
                for name, server in mcp_data["mcpServers"].items()
            }
        mcp = MCPConfig(**mcp_data)

        rules = list(settings.get("rules", []))

        return TemplateRuntimeConfig(
            template_id=template.id,
            template_name=template.name,
            version_id=version.id,
            version=version.version,
            base_class=base_class,
            llm_policy=llm_policy,
            prompts=prompts,
            execution_policy=execution_policy,
            tool_policy=tool_policy,
            mcp=mcp,
            tools=version.tools,
            prompt=version.prompt,
            rules=rules,
        )

    @staticmethod
    async def _get_version_with_template(session: AsyncSession, version_id: str) -> TemplateVersion | None:
        stmt = (
            select(TemplateVersion)
            .options(selectinload(TemplateVersion.template))
            .where(TemplateVersion.id == version_id)
        )
        result = await session.scalars(stmt)
        return result.first()


__all__ = [
    "ExecutionPolicy",
    "LLMPolicy",
    "MCPConfig",
    "MCPServerConfig",
    "PromptConfig",
    "TemplateRuntimeConfig",
    "TemplateService",
    "ToolPolicy",
    "ToolQuota",
]
