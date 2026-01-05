from __future__ import annotations

import argparse
import asyncio
import ast
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import select

from platform.persistence import AgentTemplate, TemplateVersion, Tool, create_engine, create_session_factory
from platform.persistence.repositories import ToolRepository
from platform.runtime.templates import ExecutionPolicy, LLMPolicy, PromptConfig, TemplateService, ToolPolicy

DEFAULT_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")
DEFAULT_REPO_URL = "https://github.com/sourcegraph/sgr-agent-core.git"


@dataclass
class ToolDefinition:
    name: str
    description: Optional[str] = None
    python_entrypoint: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True


@dataclass
class AgentDefinition:
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    llm_policy: dict[str, Any] = field(default_factory=dict)
    prompts: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    tool_policy: dict[str, Any] = field(default_factory=dict)
    rules: list[dict[str, Any]] = field(default_factory=list)
    activate: bool = True


def _extract_literal_assignment(file_path: Path, candidate_names: Iterable[str]) -> Optional[dict[str, Any]]:
    try:
        module = ast.parse(file_path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return None

    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in candidate_names:
                    try:
                        value = ast.literal_eval(node.value)
                        if isinstance(value, dict):
                            return value
                    except (ValueError, TypeError):
                        return None
    return None


def _parse_tool_definitions(repo_root: Path) -> list[ToolDefinition]:
    tools_dir = repo_root / "sgr_deep_research" / "core" / "tools"
    if not tools_dir.exists():
        return []

    definitions: list[ToolDefinition] = []
    for file_path in tools_dir.rglob("*.py"):
        if file_path.name == "__init__.py":
            continue
        definition = _extract_literal_assignment(file_path, ["TOOL_DEFINITION", "TOOL", "DEFINITION"])
        if not definition:
            continue
        name = definition.get("name") or file_path.stem
        description = definition.get("description")
        entrypoint = (
            definition.get("python_entrypoint")
            or definition.get("entrypoint")
            or definition.get("callable")
            or definition.get("path")
        )
        config = definition.get("config") or {k: v for k, v in definition.items() if k not in {"name", "description"}}
        definitions.append(
            ToolDefinition(
                name=name,
                description=description,
                python_entrypoint=entrypoint,
                config=config,
                is_active=bool(definition.get("is_active", True)),
            )
        )
    return definitions


def _parse_agent_definitions(repo_root: Path) -> list[AgentDefinition]:
    agent_dirs = [
        repo_root / "sgr_deep_research" / "core" / "agents",
        repo_root / "sgr_deep_research" / "agents",
    ]
    definitions: list[AgentDefinition] = []
    for agent_dir in agent_dirs:
        if not agent_dir.exists():
            continue
        for file_path in agent_dir.rglob("*.py"):
            if file_path.name == "__init__.py":
                continue
            definition = _extract_literal_assignment(file_path, ["AGENT_DEFINITION", "AGENT_TEMPLATE", "AGENT"])
            if not definition:
                continue
            name = definition.get("name") or file_path.stem
            prompts = definition.get("prompts") or {}
            if not prompts and (prompt_text := definition.get("prompt")):
                prompts = {"system": prompt_text}
            tools = list(definition.get("tools", []))
            llm_policy = definition.get("llm_policy") or definition.get("llm") or {}
            model = llm_policy.get("model") or definition.get("model") or DEFAULT_MODEL
            llm_policy.setdefault("model", model)
            execution_policy = definition.get("execution_policy") or definition.get("execution") or {}
            tool_policy = definition.get("tool_policy") or {"allowlist": tools}

            definitions.append(
                AgentDefinition(
                    name=name,
                    description=definition.get("description"),
                    prompt=definition.get("prompt"),
                    tools=tools,
                    llm_policy=llm_policy,
                    prompts=prompts,
                    execution_policy=execution_policy,
                    tool_policy=tool_policy,
                    rules=list(definition.get("rules", [])),
                    activate=bool(definition.get("activate", True)),
                )
            )
    return definitions


def _clone_repo(branch: str, target_dir: Path, *, repo_url: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    repo_path = target_dir / branch
    if repo_path.exists():
        return repo_path

    subprocess.run(
        ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(repo_path)],
        check=True,
        capture_output=True,
    )
    return repo_path


def _prepare_repo(branch: str, base_dir: Path, *, repo_url: str, repo_path: Optional[str]) -> Path:
    if repo_path:
        source = Path(repo_path)
        if not source.exists():
            msg = f"Provided repo_path does not exist: {repo_path}"
            raise FileNotFoundError(msg)
        target = base_dir / branch
        if not target.exists():
            subprocess.run(["git", "clone", str(source), str(target)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "checkout", branch], check=True, capture_output=True)
        return target

    return _clone_repo(branch, base_dir, repo_url=repo_url)


async def _upsert_tools(session_factory, tools: list[ToolDefinition]) -> None:
    async with session_factory() as session:
        repo = ToolRepository(session)
        for tool in tools:
            existing = await session.scalar(select(Tool).where(Tool.name == tool.name))
            if existing:
                await repo.update(
                    existing.id,
                    name=tool.name,
                    description=tool.description,
                    python_entrypoint=tool.python_entrypoint,
                    config=tool.config,
                    is_active=tool.is_active,
                )
            else:
                await repo.create(
                    name=tool.name,
                    description=tool.description,
                    python_entrypoint=tool.python_entrypoint,
                    config=tool.config,
                    is_active=tool.is_active,
                )
        await session.commit()


async def _ensure_template(session_factory, name: str, description: Optional[str]) -> AgentTemplate:
    async with session_factory() as session:
        existing = await session.scalar(select(AgentTemplate).where(AgentTemplate.name == name))
        if existing:
            return existing
    template_service = TemplateService(session_factory)
    return await template_service.create(name=name, description=description)


async def _version_exists(session_factory, template_id: str, agent_def: AgentDefinition) -> Optional[TemplateVersion]:
    async with session_factory() as session:
        stmt = select(TemplateVersion).where(
            TemplateVersion.template_id == template_id,
            TemplateVersion.prompt == agent_def.prompt,
        )
        return await session.scalar(stmt)


async def _seed_templates(
    session_factory,
    template_service: TemplateService,
    agents: list[AgentDefinition],
) -> None:
    for agent in agents:
        template = await _ensure_template(session_factory, agent.name, agent.description)
        existing_version = await _version_exists(session_factory, template.id, agent)
        if existing_version:
            if agent.activate and not existing_version.is_active:
                await template_service.activate(template.id, existing_version.id)
            continue

        await template_service.create_version(
            template.id,
            llm_policy=agent.llm_policy or LLMPolicy(model=DEFAULT_MODEL),
            prompts=agent.prompts or PromptConfig().model_dump(),
            execution_policy=agent.execution_policy or ExecutionPolicy().model_dump(),
            tool_policy=agent.tool_policy or ToolPolicy().model_dump(),
            tools=agent.tools,
            prompt=agent.prompt or agent.prompts.get("system"),
            activate=agent.activate,
            rules=agent.rules,
        )


async def seed_branch(
    repo_root: Path,
    session_factory,
    template_service: TemplateService,
    *,
    branch: str,
) -> None:
    tools = _parse_tool_definitions(repo_root)
    agents = _parse_agent_definitions(repo_root)

    if not tools and not agents:
        print(f"[{branch}] No definitions found at {repo_root}")
        return

    print(f"[{branch}] Seeding {len(tools)} tools and {len(agents)} agent templates from {repo_root}")
    await _upsert_tools(session_factory, tools)
    await _seed_templates(session_factory, template_service, agents)


async def main_async(args: argparse.Namespace) -> None:
    engine = create_engine(args.url)
    session_factory = create_session_factory(engine)
    template_service = TemplateService(session_factory)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            for branch in args.branch:
                repo_path = _prepare_repo(branch, base_dir, repo_url=args.repo_url, repo_path=args.repo_path)
                await seed_branch(repo_path, session_factory, template_service, branch=branch)
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed catalog tables from sgr-agent-core definitions.")
    parser.add_argument("--url", default=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db"), help="Target database URL.")
    parser.add_argument(
        "--repo-url",
        default=DEFAULT_REPO_URL,
        help="Git URL for sgr-agent-core (used when repo_path is not provided).",
    )
    parser.add_argument(
        "--repo-path",
        default=None,
        help="Existing checkout of sgr-agent-core to reuse instead of cloning.",
    )
    parser.add_argument(
        "--branch",
        action="append",
        default=["main", "sgr-memory-agent"],
        help="Branch names to ingest (can be provided multiple times).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
