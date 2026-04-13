from dataclasses import dataclass, field
import asyncio
import fnmatch
from typing import Any, Literal


PolicyEffect = Literal["allow", "deny"]


@dataclass(slots=True, frozen=True)
class PolicyObligation:
    obligation_type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.obligation_type,
            "parameters": self.parameters,
        }


@dataclass(slots=True, frozen=True)
class PolicyRule:
    rule_id: str
    effect: PolicyEffect
    reason: str
    priority: int = 0
    tenant_ids: tuple[str, ...] = ()
    principal_ids: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    tool_versions: tuple[str, ...] = ()
    obligations: tuple[PolicyObligation, ...] = ()


@dataclass(slots=True, frozen=True)
class PolicyEvaluationContext:
    tenant_id: str
    principal_id: str
    roles: tuple[str, ...]
    tool_name: str
    tool_version: str
    server_id: str


@dataclass(slots=True, frozen=True)
class PolicyDecision:
    effect: PolicyEffect
    reason: str
    obligations: tuple[PolicyObligation, ...] = ()
    rule_id: str | None = None
    is_default: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "effect": self.effect,
            "reason": self.reason,
            "ruleId": self.rule_id,
            "isDefault": self.is_default,
            "obligations": [obligation.to_payload() for obligation in self.obligations],
        }


class InMemoryPolicyStore:
    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules = tuple(self._sorted_rules(rules or []))
        self._lock = asyncio.Lock()

    def list_rules(self) -> tuple[PolicyRule, ...]:
        return self._rules

    async def get_rule(self, rule_id: str) -> PolicyRule | None:
        return next((rule for rule in self._rules if rule.rule_id == rule_id), None)

    async def upsert_rule(self, rule: PolicyRule) -> PolicyRule:
        async with self._lock:
            next_rules = [existing for existing in self._rules if existing.rule_id != rule.rule_id]
            next_rules.append(rule)
            self._rules = tuple(self._sorted_rules(next_rules))
        return rule

    async def delete_rule(self, rule_id: str) -> PolicyRule | None:
        async with self._lock:
            existing = next((rule for rule in self._rules if rule.rule_id == rule_id), None)
            if existing is None:
                return None
            self._rules = tuple(
                self._sorted_rules(
                    [rule for rule in self._rules if rule.rule_id != rule_id]
                )
            )
            return existing

    def _sorted_rules(self, rules: list[PolicyRule]) -> list[PolicyRule]:
        return sorted(rules, key=lambda rule: (-rule.priority, rule.rule_id))


class PolicyEngine:
    def __init__(self, store: InMemoryPolicyStore) -> None:
        self._store = store

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        for rule in self._store.list_rules():
            if self._matches(rule=rule, context=context):
                return PolicyDecision(
                    effect=rule.effect,
                    reason=rule.reason,
                    obligations=rule.obligations,
                    rule_id=rule.rule_id,
                    is_default=False,
                )

        return PolicyDecision(
            effect="deny",
            reason="No matching allow policy was found for this tool call.",
            obligations=(),
            rule_id=None,
            is_default=True,
        )

    def _matches(self, rule: PolicyRule, context: PolicyEvaluationContext) -> bool:
        if not self._matches_patterns(context.tenant_id, rule.tenant_ids):
            return False
        if not self._matches_patterns(context.principal_id, rule.principal_ids):
            return False
        if not self._matches_patterns(context.tool_name, rule.tool_names):
            return False
        if not self._matches_patterns(context.tool_version, rule.tool_versions):
            return False
        if rule.roles and not any(
            self._matches_patterns(role, rule.roles) for role in context.roles
        ):
            return False
        return True

    def _matches_patterns(self, value: str, patterns: tuple[str, ...]) -> bool:
        if not patterns:
            return True
        return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)
