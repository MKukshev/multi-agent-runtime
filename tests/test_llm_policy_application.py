from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable
from unittest.mock import AsyncMock, patch

import pytest

from platform.core.agents.base_agent import BaseAgent
from platform.core.llm import LLMClientFactory
from platform.runtime import (
    ChatMessage,
    ExecutionPolicy,
    LLMPolicy,
    PromptConfig,
    TemplateRuntimeConfig,
    ToolPolicy,
)


class LLMAwareAgent(BaseAgent):
    async def run(self) -> Iterable:
        message = ChatMessage.text("user", "hi")
        return await self._generate_llm_response([message.to_openai()], record_message=False)


class FakeStream:
    def __init__(self, chunks: list):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class RecordingFactory(LLMClientFactory):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.policies: list[LLMPolicy] = []

    def for_policy(self, policy: LLMPolicy):
        self.policies.append(policy)
        return self.client


@pytest.mark.anyio
async def test_llm_client_factory_resolves_policy(monkeypatch):
    monkeypatch.setenv("CUSTOM_KEY", "secret")
    policy = LLMPolicy(model="gpt-4o", base_url="https://example.ai", api_key_ref="CUSTOM_KEY")

    with patch("platform.core.llm.AsyncOpenAI") as client_cls:
        factory = LLMClientFactory()
        client = factory.for_policy(policy)

    assert client is client_cls.return_value
    client_cls.assert_called_once_with(base_url="https://example.ai", api_key="secret")
    # Cached client is reused
    assert factory.for_policy(policy) is client
    client_cls.assert_called_once()


@pytest.mark.anyio
async def test_agent_uses_llm_policy_when_calling_openai():
    policy = LLMPolicy(
        model="gpt-4o-mini",
        base_url="https://example.ai",
        api_key_ref="CUSTOM_KEY",
        temperature=0.2,
        max_tokens=64,
        streaming=True,
    )
    template_config = TemplateRuntimeConfig(
        template_id="template",
        template_name="Demo",
        version_id="v1",
        version=1,
        llm_policy=policy,
        prompts=PromptConfig(),
        execution_policy=ExecutionPolicy(),
        tool_policy=ToolPolicy(),
        tools=[],
        prompt=None,
        rules=[],
    )

    stream = FakeStream(
        [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hello "))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="world"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")]),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=stream))))
    factory = RecordingFactory(client)

    agent = LLMAwareAgent(
        task="demo",
        template_config=template_config,
        template_version_id=template_config.version_id,
        llm_client_factory=factory,
    )

    events = list(await agent.run())
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == policy.model
    assert kwargs["messages"][0]["role"] == "user"
    assert kwargs["stream"] is True
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 64
    assert factory.policies[-1] is policy

    content = "".join(event.data["choices"][0]["delta"].get("content", "") for event in events if event.event == "message")
    assert content == "hello world"
    assert events[-1].event == "done"
