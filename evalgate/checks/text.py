"""Phrase, pattern and numeric expectations read off the golden set."""

from __future__ import annotations

import re
from typing import Any

from ..dataset import Case
from .base import CheckResult, get_field, register


@register("contains")
class ContainsCheck:
    """Honours `must_contain`, `must_not_contain` and `matches` on each case."""

    name = "contains"

    def __init__(
        self, root: Any = None, field: str = "answer", case_sensitive: bool = False, **_: Any
    ) -> None:
        self.field = field
        self.case_sensitive = case_sensitive

    def run(self, case: Case, output: dict[str, Any]) -> CheckResult:
        value = get_field(output, self.field)
        if not isinstance(value, str):
            return CheckResult(self.name, False, 0.0, f"{self.field} is not a string")

        haystack = value if self.case_sensitive else value.lower()
        failures: list[str] = []
        expectations = 0

        for phrase in case.expect.get("must_contain", []):
            expectations += 1
            needle = phrase if self.case_sensitive else phrase.lower()
            if needle not in haystack:
                failures.append(f"missing {phrase!r}")

        for phrase in case.expect.get("must_not_contain", []):
            expectations += 1
            needle = phrase if self.case_sensitive else phrase.lower()
            if needle in haystack:
                failures.append(f"should not say {phrase!r}")

        for pattern in case.expect.get("matches", []):
            expectations += 1
            flags = 0 if self.case_sensitive else re.IGNORECASE
            if not re.search(pattern, value, flags):
                failures.append(f"does not match /{pattern}/")

        if expectations == 0:
            return CheckResult(self.name, True, 1.0, "no phrase expectations on this case")

        score = (expectations - len(failures)) / expectations
        return CheckResult(
            check=self.name,
            passed=not failures,
            score=score,
            detail="; ".join(failures[:4]) if failures else f"{expectations} phrase expectations met",
            evidence={"failures": failures},
        )


@register("numeric")
class NumericCheck:
    """Compares numeric output fields against `expect` within a tolerance."""

    name = "numeric"

    def __init__(
        self, root: Any = None, fields: list[str] | None = None, tolerance: float = 0.0, **_: Any
    ) -> None:
        self.fields = fields or []
        self.tolerance = float(tolerance)

    def run(self, case: Case, output: dict[str, Any]) -> CheckResult:
        targets = self.fields or [k for k in case.expect if isinstance(case.expect[k], (int, float))]
        checked = 0
        failures: list[str] = []
        for name in targets:
            if name not in case.expect:
                continue
            expected = case.expect[name]
            if not isinstance(expected, (int, float)) or isinstance(expected, bool):
                continue
            checked += 1
            actual = get_field(output, name)
            if not isinstance(actual, (int, float)) or isinstance(actual, bool):
                failures.append(f"{name} is {actual!r}, expected a number")
                continue
            if abs(actual - expected) > self.tolerance:
                failures.append(f"{name}={actual} differs from {expected} by more than {self.tolerance}")

        if checked == 0:
            return CheckResult(self.name, True, 1.0, "no numeric expectations on this case")
        score = (checked - len(failures)) / checked
        return CheckResult(
            check=self.name,
            passed=not failures,
            score=score,
            detail="; ".join(failures[:4]) if failures else f"{checked} numeric fields within tolerance",
            evidence={"failures": failures},
        )
