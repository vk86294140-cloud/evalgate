"""Regression tracking against a stored baseline.

A falling pass rate is easy to miss when the suite grows. What you actually
want to block is the specific case that used to pass and now does not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runner import RunReport


@dataclass
class Delta:
    regressions: list[tuple[str, str]]
    fixes: list[tuple[str, str]]
    new_cases: list[str]
    dropped_cases: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "regressions": [{"case": c, "check": k} for c, k in self.regressions],
            "fixes": [{"case": c, "check": k} for c, k in self.fixes],
            "new_cases": self.new_cases,
            "dropped_cases": self.dropped_cases,
        }


def save_baseline(path: str | Path, report: RunReport) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite": report.suite,
        "pass_rate": round(report.pass_rate, 4),
        "outcomes": report.outcome_map(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_baseline(path: str | Path) -> dict[str, dict[str, bool]]:
    path = Path(path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    outcomes = payload.get("outcomes", {})
    return {str(k): {str(ck): bool(cv) for ck, cv in v.items()} for k, v in outcomes.items()}


def compare(report: RunReport, baseline: dict[str, dict[str, bool]]) -> Delta:
    current = report.outcome_map()
    regressions: list[tuple[str, str]] = []
    fixes: list[tuple[str, str]] = []

    for case_id, checks in current.items():
        before = baseline.get(case_id)
        if before is None:
            continue
        for name, now_passed in checks.items():
            was_passed = before.get(name)
            if was_passed is None:
                continue
            if was_passed and not now_passed:
                regressions.append((case_id, name))
            elif not was_passed and now_passed:
                fixes.append((case_id, name))

    return Delta(
        regressions=sorted(regressions),
        fixes=sorted(fixes),
        new_cases=sorted(set(current) - set(baseline)),
        dropped_cases=sorted(set(baseline) - set(current)),
    )
