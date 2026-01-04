"""Template service for managing agent templates and runtime configuration."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform.retrieval.embeddings import EmbeddingProvider
from platform.persistence import AgentTemplate, TemplateRepository, TemplateVersion


class LLMPolicy(BaseModel):
    base_url: Optional[str] = None
    api_key_ref: Optional[str] = None
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    streaming: bool = False


class PromptConfig(BaseModel):
    system: Optional[str] = None
    initial_user: Optional[str] = None
    clarification: Optional[str] = None


class ExecutionPolicy(BaseModel):
    max_iterations: Optional[int] = None
    max_clarifications: Optional[int] = None
    max_searches: Optional[int] = None
    time_budget_seconds: Optional[int] = None


class ToolPolicy(BaseModel):
    required_tools: list[str] = Field(default_factory=list)
    allowlist: list[str] = Field(default_factory=list)
    denylist: list[str] = Field(default_factory=list)
    max_tools_in_prompt: Optional[int] = None
    selection_strategy: Optional[str] = None


class TemplateRuntimeConfig(BaseModel):
    template_id: str
    template_name: str
    version_id: str
    version: int
    llm_policy: LLMPolicy
    prompts: PromptConfig
    execution_policy: ExecutionPolicy
    tool_policy: ToolPolicy
    tools: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    rules: list[dict[str, Any]] = Field(default_factory=list)


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
        llm_policy = LLMPolicy(**settings.get("llm_policy", {}))
        prompts = PromptConfig(**settings.get("prompts", {}))
        execution_policy = ExecutionPolicy(**settings.get("execution_policy", {}))
        tool_policy = ToolPolicy(**settings.get("tool_policy", {}))
        rules = list(settings.get("rules", []))

        return TemplateRuntimeConfig(
            template_id=template.id,
            template_name=template.name,
            version_id=version.id,
            version=version.version,
            llm_policy=llm_policy,
            prompts=prompts,
            execution_policy=execution_policy,
            tool_policy=tool_policy,
            tools=version.tools,
            prompt=version.prompt,
            rules=rules,
        )
