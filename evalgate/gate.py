"""Turn a run into a pass/fail verdict CI can act on."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .baseline import Delta
from .config import Gate
from .runner import RunReport


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reasons": self.reasons, "notes": self.notes}


def evaluate(gate: Gate, report: RunReport, delta: Delta | None = None) -> GateResult:
    reasons: list[str] = []
    notes: list[str] = []

    errored = [c.id for c in report.cases if c.error]
    if errored:
        reasons.append(f"{len(errored)} case(s) errored: {', '.join(errored[:5])}")

    if report.pass_rate < gate.min_pass_rate:
        reasons.append(f"pass rate {report.pass_rate:.1%} is below the required {gate.min_pass_rate:.1%}")

    rates = report.check_rates()
    for name, floor in gate.per_check.items():
        actual = rates.get(name)
        if actual is None:
            notes.append(f"gate mentions check {name!r} but the suite never ran it")
            continue
        if actual < floor:
            reasons.append(f"check {name!r} at {actual:.1%} is below its floor of {floor:.1%}")

    if delta is not None:
        if len(delta.regressions) > gate.max_regressions:
            sample = ", ".join(f"{c}/{k}" for c, k in delta.regressions[:5])
            reasons.append(
                f"{len(delta.regressions)} regression(s) against the baseline, "
                f"max allowed {gate.max_regressions}: {sample}"
            )
        if delta.fixes:
            notes.append(f"{len(delta.fixes)} case(s) now pass that did not before")
        if delta.new_cases:
            notes.append(f"{len(delta.new_cases)} new case(s) not in the baseline")

    return GateResult(passed=not reasons, reasons=reasons, notes=notes)
