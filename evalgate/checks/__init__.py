"""Built-in checks. Importing the package registers them."""

from .base import Check, CheckResult, build_check, known_checks, register
from .grounding import GroundingCheck
from .structure import SchemaCheck, validate
from .text import ContainsCheck, NumericCheck

__all__ = [
    "Check",
    "CheckResult",
    "ContainsCheck",
    "GroundingCheck",
    "NumericCheck",
    "SchemaCheck",
    "build_check",
    "known_checks",
    "register",
    "validate",
]
