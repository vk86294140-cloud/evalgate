"""The golden set: one JSON object per line."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DatasetError(ValueError):
    """The golden set is malformed."""


@dataclass
class Case:
    id: str
    input: dict[str, Any]
    expect: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


def load_dataset(path: str | Path) -> list[Case]:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"dataset not found: {path}")
    cases = list(_iter_cases(path))
    if not cases:
        raise DatasetError(f"{path} contains no cases")
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise DatasetError(f"duplicate case id: {case.id}")
        seen.add(case.id)
    return cases


def _iter_cases(path: Path) -> Iterator[Case]:
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{path}:{lineno}: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise DatasetError(f"{path}:{lineno}: each line must be a JSON object")
        if "input" not in raw:
            raise DatasetError(f"{path}:{lineno}: case is missing 'input'")
        yield Case(
            id=str(raw.get("id") or f"case-{lineno}"),
            input=raw["input"],
            expect=raw.get("expect") or {},
            tags=list(raw.get("tags") or []),
        )
