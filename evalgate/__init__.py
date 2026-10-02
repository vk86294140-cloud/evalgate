"""evalgate - a quality gate for LLM and agent output.

Point it at a golden set and a callable, and it tells CI whether the change you
are about to merge made the system worse.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .baseline import Delta, compare, load_baseline, save_baseline
from .checks.base import CheckResult, build_check, known_checks, register
from .config import Config, ConfigError, Gate
from .dataset import Case, load_dataset
from .gate import GateResult, evaluate
from .runner import CaseResult, RunReport, run_suite

__all__ = [
    "Case",
    "CaseResult",
    "CheckResult",
    "Config",
    "ConfigError",
    "Delta",
    "Gate",
    "GateResult",
    "RunReport",
    "__version__",
    "build_check",
    "compare",
    "evaluate",
    "known_checks",
    "load_baseline",
    "load_dataset",
    "register",
    "run_suite",
    "save_baseline",
]
