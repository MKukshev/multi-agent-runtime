"""
Rules engine for template-defined discriminators.

Expected JSON structure inside template settings:
{
  "apply_to": ["pre_retrieval", "post_retrieval"],
  "when": {
    "iteration_gte": "max_iterations",
    "searches_used_gte": 2,
    "clarifications_used_gte": 1,
    "state_equals": "ACTIVE"
  },
  "actions": {
    "exclude": ["SearchTool"],
    "keep_only": ["FinalAnswer", "CreateReport"],
    "set_stage": "finalization"
  }
}

Thresholds can be numeric or string references to fields in `template.execution_policy`
such as `"max_iterations"`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable, Mapping, MutableSequence, Sequence

from pydantic import BaseModel, Field


class RulePhase(StrEnum):
    PRE_RETRIEVAL = "pre_retrieval"
    POST_RETRIEVAL = "post_retrieval"


class RuleCondition(BaseModel):
    """Supported rule conditions expressed in template JSON."""

    iteration_gte: int | str | None = None
    searches_used_gte: int | str | None = None
    clarifications_used_gte: int | str | None = None
    state_equals: str | None = None

    def matches(self, session: Any | None, template: Any | None) -> bool:
        if self.iteration_gte is not None:
            if not self._compare_threshold(session, template, "iteration", self.iteration_gte):
                return False
        if self.searches_used_gte is not None:
            if not self._compare_threshold(session, template, "searches_used", self.searches_used_gte):
                return False
        if self.clarifications_used_gte is not None:
            if not self._compare_threshold(session, template, "clarifications_used", self.clarifications_used_gte):
                return False
        if self.state_equals is not None:
            current_state = getattr(session, "state", None) if session is not None else None
            if current_state is None and session is not None:
                current_state = getattr(session, "data", {}).get("state")
            if current_state != self.state_equals:
                return False
        return True

    def _compare_threshold(self, session: Any | None, template: Any | None, key: str, threshold: int | str) -> bool:
        current_value = None
        if session is not None:
            current_value = getattr(session, "data", {}).get(key)
        current_value = _coerce_int(current_value)
        target = _resolve_threshold(threshold, template)
        if target is None:
            return False
        if current_value is None:
            return False
        return current_value >= target


class RuleAction(BaseModel):
    """Actions supported by the rules engine."""

    exclude: list[str] = Field(default_factory=list)
    keep_only: list[str] = Field(default_factory=list)
    set_stage: str | None = None


class Rule(BaseModel):
    """A single rule describing conditions and actions."""

    apply_to: set[RulePhase] = Field(
        default_factory=lambda: {RulePhase.PRE_RETRIEVAL, RulePhase.POST_RETRIEVAL}
    )
    when: RuleCondition = Field(default_factory=RuleCondition)
    actions: RuleAction = Field(default_factory=RuleAction)

    model_config = {"use_enum_values": True}


class RuleDecision(BaseModel):
    exclude: list[str] = Field(default_factory=list)
    keep_only: list[str] | None = None
    stage: str | None = None

    def apply(self, tools: Iterable[str]) -> list[str]:
        keep_set = set(self.keep_only) if self.keep_only is not None else None
        exclude_set = set(self.exclude)
        ordered: MutableSequence[str] = []
        for tool in tools:
            if tool in exclude_set:
                continue
            if keep_set is not None and tool not in keep_set:
                continue
            ordered.append(tool)
        return list(ordered)

    def apply_actions(self, actions: RuleAction) -> None:
        if actions.exclude:
            self.exclude = list(dict.fromkeys(self.exclude + list(actions.exclude)))
        if actions.keep_only:
            keep_set = set(self.keep_only) if self.keep_only is not None else None
            new_keep = set(actions.keep_only)
            self.keep_only = list(new_keep & keep_set) if keep_set is not None else list(new_keep)
        if actions.set_stage is not None:
            self.stage = actions.set_stage


class RulesEngine:
    """Simple rules engine for filtering tool availability based on session/template state."""

    def evaluate(self, session: Any | None, template: Any | None, *, phase: RulePhase | None = None) -> RuleDecision:
        rules = self._extract_rules(template)
        decision = RuleDecision()
        for rule in rules:
            if phase is not None and phase not in rule.apply_to:
                continue
            if rule.when.matches(session, template):
                decision.apply_actions(rule.actions)
        return decision

    def _extract_rules(self, template: Any | None) -> Sequence[Rule]:
        if template is None:
            return []
        raw_rules: list[Mapping[str, Any]] = []
        if isinstance(template, Mapping):
            raw_rules = list(template.get("rules", []))
        else:
            raw_rules = list(getattr(template, "rules", []) or [])
        parsed: list[Rule] = []
        for raw in raw_rules:
            try:
                parsed.append(Rule.model_validate(raw))
            except Exception:
                continue
        return parsed


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _resolve_threshold(value: int | str, template: Any | None) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    if template is None:
        return None
    policy = getattr(template, "execution_policy", None)
    if policy is not None and hasattr(policy, value):
        candidate = getattr(policy, value)
        return _coerce_int(candidate)
    return None


__all__ = ["Rule", "RuleAction", "RuleCondition", "RuleDecision", "RulePhase", "RulesEngine"]
