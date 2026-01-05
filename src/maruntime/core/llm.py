from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from maruntime.runtime.templates import LLMPolicy


def content_to_text(content: Any) -> str:
    """Normalize OpenAI content blocks (dicts, models, or strings) into plain text."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text_value = getattr(item, "text", None)
            if isinstance(item, dict):
                text_value = item.get("text", text_value)
            parts.append(str(text_value) if text_value is not None else str(item))
        return "".join(parts)
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
    text_attr = getattr(content, "text", None)
    if text_attr is not None:
        return str(text_attr)
    return str(content)


class LLMClientFactory:
    """Factory that builds OpenAI clients using the provided LLM policy settings."""

    def __init__(self, *, default_api_key_env: str = "OPENAI_API_KEY") -> None:
        self._default_api_key_env = default_api_key_env
        self._cache: dict[tuple[str | None, str | None], AsyncOpenAI] = {}

    def for_policy(self, policy: LLMPolicy) -> AsyncOpenAI:
        api_key = self._resolve_api_key(policy.api_key_ref)
        cache_key = (policy.base_url, api_key)
        if cache_key not in self._cache:
            kwargs: dict[str, Any] = {}
            if policy.base_url:
                kwargs["base_url"] = policy.base_url
            if api_key:
                kwargs["api_key"] = api_key
            self._cache[cache_key] = AsyncOpenAI(**kwargs)
        return self._cache[cache_key]

    def _resolve_api_key(self, api_key_ref: str | None) -> str | None:
        if api_key_ref:
            return os.getenv(api_key_ref)
        return os.getenv(self._default_api_key_env)


__all__ = ["LLMClientFactory", "content_to_text"]
