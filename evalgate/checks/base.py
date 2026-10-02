"""Check protocol and the registry every check type registers into."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..dataset import Case


@dataclass
class CheckResult:
    check: str
    passed: bool
    score: float = 0.0
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "passed": self.passed,
            "score": round(self.score, 4),
            "detail": self.detail,
            "evidence": self.evidence,
        }


class Check(Protocol):
    name: str

    def run(self, case: Case, output: dict[str, Any]) -> CheckResult: ...


_REGISTRY: dict[str, Callable[..., Check]] = {}


def register(type_name: str) -> Callable[[Callable[..., Check]], Callable[..., Check]]:
    def decorator(factory: Callable[..., Check]) -> Callable[..., Check]:
        _REGISTRY[type_name] = factory
        return factory

    return decorator


def build_check(spec: dict[str, Any], root: Any = None) -> Check:
    spec = dict(spec)
    type_name = spec.pop("type", None)
    if type_name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise ValueError(f"unknown check type {type_name!r} (known: {known})")
    factory = _REGISTRY[type_name]
    try:
        return factory(root=root, **spec)
    except TypeError as exc:
        raise ValueError(f"bad options for check {type_name!r}: {exc}") from exc


def known_checks() -> list[str]:
    return sorted(_REGISTRY)


def get_field(output: dict[str, Any], path: str) -> Any:
    """Dotted lookup so a check can point at output['result']['answer']."""
    value: Any = output
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value
