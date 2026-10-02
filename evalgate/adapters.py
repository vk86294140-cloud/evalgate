"""Calling the system under test.

Two shapes cover almost everything: a Python callable in this repo, or a
command that reads a JSON case on stdin and writes a JSON result on stdout.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .config import SystemSpec


class AdapterError(RuntimeError):
    """The system under test could not be run, or did not return JSON."""


class Adapter(Protocol):
    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def build_adapter(spec: SystemSpec, root: Path) -> Adapter:
    if spec.type == "python":
        return _python_adapter(spec, root)
    return _command_adapter(spec, root)


def _python_adapter(spec: SystemSpec, root: Path) -> Adapter:
    if ":" not in spec.target:
        raise AdapterError(f"python target must be 'module:callable', got {spec.target!r}")
    module_name, _, attr = spec.target.partition(":")
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Load a target that lives beside the config from its file, rather than
    # through the import cache. Two suites in one process often both name
    # their system `system.py`, and the second would otherwise silently get
    # the first one's module.
    local = root / (module_name.replace(".", "/") + ".py")
    if local.exists():
        loader_spec = importlib.util.spec_from_file_location(module_name, local)
        if loader_spec is None or loader_spec.loader is None:
            raise AdapterError(f"cannot load {local}")
        module = importlib.util.module_from_spec(loader_spec)
        sys.modules[module_name] = module
        try:
            loader_spec.loader.exec_module(module)
        except Exception as exc:
            raise AdapterError(f"importing {local} failed: {exc}") from exc
    else:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise AdapterError(f"cannot import {module_name!r} from {root}") from exc
    fn: Callable[..., Any] | None = getattr(module, attr, None)
    if not callable(fn):
        raise AdapterError(f"{spec.target} is not callable")

    def run(payload: dict[str, Any]) -> dict[str, Any]:
        result = fn(payload)
        if not isinstance(result, dict):
            raise AdapterError(f"{spec.target} returned {type(result).__name__}, expected a dict")
        return result

    return run


def split_command(target: str | list[str]) -> list[str]:
    """Split a command string into argv.

    On Windows a path is full of backslashes, so POSIX splitting would eat
    them as escapes; non-POSIX splitting keeps them but leaves the surrounding
    quotes attached to the token, which `subprocess` then treats as part of the
    filename. Strip them back off.
    """
    if not isinstance(target, str):
        return list(target)
    if os.name == "nt":
        return [part.strip('"') for part in shlex.split(target, posix=False)]
    return shlex.split(target)


def _command_adapter(spec: SystemSpec, root: Path) -> Adapter:
    argv = split_command(spec.target)
    if not argv:
        raise AdapterError("system.target is an empty command")

    def run(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(root),
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=spec.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"system timed out after {spec.timeout_s}s") from exc
        if proc.returncode != 0:
            raise AdapterError(f"system exited {proc.returncode}: {proc.stderr.strip()[:400]}")
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"system stdout was not JSON: {proc.stdout.strip()[:200]!r}") from exc
        if not isinstance(result, dict):
            raise AdapterError("system must emit a JSON object")
        return result

    return run
