"""Rendering: terminal for humans, markdown for pull requests, JSON and JUnit
for everything else."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .baseline import Delta
from .gate import GateResult
from .runner import RunReport

TICK = "PASS"
CROSS = "FAIL"


def terminal(report: RunReport, gate: GateResult, delta: Delta | None = None) -> str:
    lines = [f"evalgate: {report.suite}", ""]
    for case in report.cases:
        mark = TICK if case.passed else CROSS
        lines.append(f"  [{mark}] {case.id}  ({case.duration_ms:.0f}ms)")
        if case.error:
            lines.append(f"         error: {case.error}")
        for check in case.checks:
            if not check.passed:
                lines.append(f"         {check.check}: {check.detail}")

    lines.append("")
    lines.append(f"  {report.passed}/{report.total} cases passed ({report.pass_rate:.1%})")
    for name, rate in sorted(report.check_rates().items()):
        lines.append(f"    {name:<12} {rate:.1%}")

    if delta and (delta.regressions or delta.fixes):
        lines.append("")
        for case_id, check_name in delta.regressions:
            lines.append(f"  regression: {case_id} / {check_name}")
        for case_id, check_name in delta.fixes:
            lines.append(f"  fixed:      {case_id} / {check_name}")

    lines.append("")
    if gate.passed:
        lines.append("  gate: PASSED")
    else:
        lines.append("  gate: FAILED")
        for reason in gate.reasons:
            lines.append(f"    - {reason}")
    for note in gate.notes:
        lines.append(f"    note: {note}")
    return "\n".join(lines)


def markdown(report: RunReport, gate: GateResult, delta: Delta | None = None) -> str:
    status = "passed" if gate.passed else "failed"
    out = [
        f"### evalgate: `{report.suite}` — gate {status}",
        "",
        f"**{report.passed}/{report.total} cases passed** ({report.pass_rate:.1%})",
        "",
        "| check | pass rate |",
        "| --- | --- |",
    ]
    for name, rate in sorted(report.check_rates().items()):
        out.append(f"| {name} | {rate:.1%} |")

    failures = [c for c in report.cases if not c.passed]
    if failures:
        out += ["", "<details><summary>Failing cases</summary>", ""]
        for case in failures:
            detail = case.error or "; ".join(f"{c.check}: {c.detail}" for c in case.checks if not c.passed)
            out.append(f"- `{case.id}` — {detail}")
        out += ["", "</details>"]

    if delta and delta.regressions:
        out += ["", "**Regressions against baseline**", ""]
        out += [f"- `{case_id}` / {check}" for case_id, check in delta.regressions]

    if gate.reasons:
        out += ["", "**Why the gate failed**", ""]
        out += [f"- {r}" for r in gate.reasons]

    return "\n".join(out) + "\n"


def junit(report: RunReport) -> str:
    suite = ET.Element(
        "testsuite",
        name=report.suite,
        tests=str(report.total),
        failures=str(report.total - report.passed),
    )
    for case in report.cases:
        node = ET.SubElement(
            suite,
            "testcase",
            classname=report.suite,
            name=case.id,
            time=f"{case.duration_ms / 1000:.3f}",
        )
        if case.error:
            ET.SubElement(node, "error", message=case.error[:200]).text = case.error
        elif not case.passed:
            detail = "\n".join(f"{c.check}: {c.detail}" for c in case.checks if not c.passed)
            ET.SubElement(node, "failure", message=detail[:200]).text = detail
    return ET.tostring(suite, encoding="unicode")


def write_artifacts(
    report: RunReport,
    gate: GateResult,
    delta: Delta | None,
    json_path: str | Path | None = None,
    markdown_path: str | Path | None = None,
    junit_path: str | Path | None = None,
) -> list[Path]:
    written: list[Path] = []
    if json_path:
        payload = {"run": report.as_dict(), "gate": gate.as_dict()}
        if delta:
            payload["delta"] = delta.as_dict()
        written.append(_write(json_path, json.dumps(payload, indent=2) + "\n"))
    if markdown_path:
        written.append(_write(markdown_path, markdown(report, gate, delta)))
    if junit_path:
        written.append(_write(junit_path, junit(report)))
    return written


def _write(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
