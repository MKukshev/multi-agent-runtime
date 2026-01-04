from __future__ import annotations

from pydantic import BaseModel, Field


class SecurityError(PermissionError):
    """Raised when a request violates security policies."""


class AllowlistPolicy(BaseModel):
    """Allowlist for model/template usage."""

    models: set[str] = Field(default_factory=set)

    def is_allowed(self, model: str) -> bool:
        if not self.models:
            return True
        return model in self.models


class RiskPolicy(BaseModel):
    """Lightweight risk policy detecting disallowed content."""

    banned_terms: list[str] = Field(default_factory=list)

    def is_safe(self, text: str) -> bool:
        lowered = text.lower()
        return all(term.lower() not in lowered for term in self.banned_terms)


class SecurityPolicy(BaseModel):
    """Aggregate security policy for gateway requests."""

    allowlist: AllowlistPolicy = Field(default_factory=AllowlistPolicy)
    risk: RiskPolicy = Field(default_factory=RiskPolicy)

    def validate(self, *, model: str, prompt: str) -> None:
        if not self.allowlist.is_allowed(model):
            msg = f"Model '{model}' is not allowlisted"
            raise SecurityError(msg)
        if not self.risk.is_safe(prompt):
            msg = "Prompt violates risk policy"
            raise SecurityError(msg)


__all__ = ["AllowlistPolicy", "RiskPolicy", "SecurityError", "SecurityPolicy"]
