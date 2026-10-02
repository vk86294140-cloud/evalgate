"""evalgate command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .baseline import compare, load_baseline, save_baseline
from .checks.base import known_checks
from .config import Config, ConfigError
from .dataset import DatasetError
from .gate import evaluate
from .report import terminal, write_artifacts
from .runner import run_suite


def _load(path: str) -> Config:
    try:
        return Config.load(path)
    except ConfigError as exc:
        print(f"evalgate: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


def cmd_run(args: argparse.Namespace) -> int:
    config = _load(args.config)
    try:
        report = run_suite(config, only=args.only)
    except (DatasetError, ValueError) as exc:
        print(f"evalgate: {exc}", file=sys.stderr)
        return 2

    baseline_path = Path(args.baseline) if args.baseline else config.baseline
    delta = None
    if baseline_path and Path(baseline_path).exists():
        delta = compare(report, load_baseline(baseline_path))

    gate = evaluate(config.gate, report, delta)
    print(terminal(report, gate, delta))

    written = write_artifacts(
        report,
        gate,
        delta,
        json_path=args.json,
        markdown_path=args.markdown,
        junit_path=args.junit,
    )
    for path in written:
        print(f"  wrote {path}")

    if args.update_baseline and baseline_path:
        save_baseline(baseline_path, report)
        print(f"  baseline updated: {baseline_path}")

    return 0 if gate.passed else 1


def cmd_baseline(args: argparse.Namespace) -> int:
    config = _load(args.config)
    path = Path(args.out) if args.out else config.baseline
    if not path:
        print("evalgate: no baseline path in the config and none given with --out", file=sys.stderr)
        return 2
    report = run_suite(config)
    save_baseline(path, report)
    print(f"baseline written to {path} ({report.passed}/{report.total} passing)")
    return 0


def cmd_checks(_args: argparse.Namespace) -> int:
    for name in known_checks():
        print(name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evalgate", description="A quality gate for LLM output.")
    parser.add_argument("--version", action="version", version=f"evalgate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the suite and apply the gate")
    run.add_argument("-c", "--config", default="evalgate.yaml")
    run.add_argument("--only", action="append", help="case id or tag (repeatable)")
    run.add_argument("--baseline", help="override the baseline path")
    run.add_argument("--update-baseline", action="store_true", help="rewrite the baseline after the run")
    run.add_argument("--json", help="write the full result as JSON")
    run.add_argument("--markdown", help="write a pull-request comment body")
    run.add_argument("--junit", help="write JUnit XML")
    run.set_defaults(func=cmd_run)

    base = sub.add_parser("baseline", help="record the current outcomes as the baseline")
    base.add_argument("-c", "--config", default="evalgate.yaml")
    base.add_argument("-o", "--out")
    base.set_defaults(func=cmd_baseline)

    checks = sub.add_parser("checks", help="list the available check types")
    checks.set_defaults(func=cmd_checks)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
