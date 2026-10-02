"""Run every case through the system under test and score it."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .adapters import AdapterError, build_adapter
from .checks.base import CheckResult, build_check
from .config import Config
from .dataset import Case, load_dataset


@dataclass
class CaseResult:
    id: str
    passed: bool
    duration_ms: float
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "tags": self.tags,
            "checks": [c.as_dict() for c in self.checks],
        }


@dataclass
class RunReport:
    suite: str
    cases: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def check_rates(self) -> dict[str, float]:
        totals: dict[str, list[int]] = {}
        for case in self.cases:
            for check in case.checks:
                bucket = totals.setdefault(check.check, [0, 0])
                bucket[0] += int(check.passed)
                bucket[1] += 1
        return {name: (hits / count if count else 0.0) for name, (hits, count) in totals.items()}

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "check_rates": {k: round(v, 4) for k, v in self.check_rates().items()},
            "cases": [c.as_dict() for c in self.cases],
        }

    def outcome_map(self) -> dict[str, dict[str, bool]]:
        """case id -> check name -> passed. The shape a baseline stores."""
        return {case.id: {c.check: c.passed for c in case.checks} for case in self.cases}


def run_suite(config: Config, only: list[str] | None = None) -> RunReport:
    cases = load_dataset(config.dataset)
    if only:
        wanted = set(only)
        cases = [c for c in cases if c.id in wanted or wanted & set(c.tags)]
        if not cases:
            raise ValueError(f"no cases matched {sorted(wanted)}")

    adapter = build_adapter(config.system, config.root)
    checks = [build_check(spec, root=config.root) for spec in config.checks]

    results: list[CaseResult] = []
    for case in cases:
        results.append(_run_case(case, adapter, checks))
    return RunReport(suite=config.name, cases=results)


def _run_case(case: Case, adapter: Any, checks: list[Any]) -> CaseResult:
    started = time.perf_counter()
    try:
        output = adapter(dict(case.input))
    except AdapterError as exc:
        return CaseResult(
            id=case.id,
            passed=False,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=str(exc),
            tags=case.tags,
        )
    except Exception as exc:  # the system under test is user code; keep the suite alive
        return CaseResult(
            id=case.id,
            passed=False,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(exc).__name__}: {exc}",
            tags=case.tags,
        )

    check_results = [check.run(case, output) for check in checks]
    return CaseResult(
        id=case.id,
        passed=all(r.passed for r in check_results),
        duration_ms=(time.perf_counter() - started) * 1000,
        checks=check_results,
        tags=case.tags,
    )
