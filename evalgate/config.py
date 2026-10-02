"""Load and validate an evalgate config file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """The config file is missing something evalgate needs."""


@dataclass
class SystemSpec:
    type: str
    target: str
    timeout_s: float = 60.0

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> SystemSpec:
        kind = raw.get("type")
        if kind not in {"python", "command"}:
            raise ConfigError(f"system.type must be 'python' or 'command', got {kind!r}")
        target = raw.get("target")
        if not target:
            raise ConfigError("system.target is required")
        return cls(type=kind, target=target, timeout_s=float(raw.get("timeout_s", 60)))


@dataclass
class Gate:
    min_pass_rate: float = 1.0
    max_regressions: int = 0
    per_check: dict[str, float] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Gate:
        gate = cls(
            min_pass_rate=float(raw.get("min_pass_rate", 1.0)),
            max_regressions=int(raw.get("max_regressions", 0)),
            per_check={k: float(v) for k, v in (raw.get("per_check") or {}).items()},
        )
        if not 0.0 <= gate.min_pass_rate <= 1.0:
            raise ConfigError("gate.min_pass_rate must be between 0 and 1")
        return gate


@dataclass
class Config:
    name: str
    root: Path
    dataset: Path
    system: SystemSpec
    checks: list[dict[str, Any]]
    gate: Gate
    baseline: Path | None = None

    @classmethod
    def load(cls, path: str | Path) -> Config:
        path = Path(path).resolve()
        if not path.exists():
            raise ConfigError(f"config not found: {path}")
        raw = _read_structured(path)
        root = path.parent

        for required in ("dataset", "system", "checks"):
            if required not in raw:
                raise ConfigError(f"missing required key: {required}")
        if not raw["checks"]:
            raise ConfigError("checks must not be empty")

        baseline = raw.get("baseline")
        return cls(
            name=raw.get("name", path.parent.name),
            root=root,
            dataset=(root / raw["dataset"]).resolve(),
            system=SystemSpec.parse(raw["system"]),
            checks=list(raw["checks"]),
            gate=Gate.parse(raw.get("gate") or {}),
            baseline=(root / baseline).resolve() if baseline else None,
        )


def _read_structured(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install extras
        raise ConfigError(
            f"{path.name} is YAML but PyYAML is not installed; install evalgate[yaml] or use a .json config"
        ) from exc
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path.name} must contain a mapping at the top level")
    return loaded
