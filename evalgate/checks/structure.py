"""Structural validation: does the output have the shape the caller promised?

A deliberately small JSON Schema subset - type, required, properties, enum,
items, minimum/maximum, minLength - so evalgate stays dependency-free. It
covers the mistakes an LLM actually makes: a missing field, a string where a
number belongs, an invented enum value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..dataset import Case
from .base import CheckResult, register

_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        allowed = _TYPES.get(expected)
        if allowed is None:
            errors.append(f"{path}: schema uses unsupported type {expected!r}")
            return errors
        if expected == "integer" and isinstance(instance, bool):
            errors.append(f"{path}: expected integer, got boolean")
            return errors
        if expected == "number" and isinstance(instance, bool):
            errors.append(f"{path}: expected number, got boolean")
            return errors
        if not isinstance(instance, allowed):
            errors.append(f"{path}: expected {expected}, got {type(instance).__name__}")
            return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required field {key!r}")
        for key, subschema in (schema.get("properties") or {}).items():
            if key in instance:
                errors.extend(validate(instance[key], subschema, f"{path}.{key}"))

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate(item, schema["items"], f"{path}[{i}]"))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} is above maximum {schema['maximum']}")

    if isinstance(instance, str) and "minLength" in schema and len(instance) < schema["minLength"]:
        errors.append(f"{path}: string shorter than minLength {schema['minLength']}")

    return errors


@register("schema")
class SchemaCheck:
    name = "schema"

    def __init__(self, root: Path | None = None, schema: Any = None, **_: Any) -> None:
        if schema is None:
            raise TypeError("schema check needs a 'schema' path or inline object")
        if isinstance(schema, str):
            schema_path = Path(schema)
            if root is not None and not schema_path.is_absolute():
                schema_path = Path(root) / schema_path
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if not isinstance(schema, dict):
            raise TypeError("schema must be a mapping or a path to one")
        self.schema = schema

    def run(self, case: Case, output: dict[str, Any]) -> CheckResult:
        errors = validate(output, self.schema)
        return CheckResult(
            check=self.name,
            passed=not errors,
            score=0.0 if errors else 1.0,
            detail="; ".join(errors[:4]) if errors else "output matches the schema",
            evidence={"errors": errors},
        )
