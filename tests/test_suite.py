from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalgate.baseline import compare, load_baseline, save_baseline
from evalgate.cli import main
from evalgate.config import Config, ConfigError, Gate
from evalgate.dataset import DatasetError, load_dataset
from evalgate.gate import evaluate
from evalgate.report import junit, markdown, terminal
from evalgate.runner import run_suite

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "support_bot" / "evalgate.yaml"


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    (tmp_path / "golden.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "good",
                        "input": {"q": "x", "context": "The sky is blue today."},
                        "expect": {"must_contain": ["blue"]},
                    }
                ),
                json.dumps(
                    {
                        "id": "bad",
                        "input": {"q": "y", "context": "The sky is blue today."},
                        "expect": {"must_contain": ["green"]},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "sut.py").write_text(
        "def answer(payload):\n"
        "    return {'answer': 'The sky is blue today.',\n"
        "            'citations': ['The sky is blue today.'],\n"
        "            'context': payload['context']}\n",
        encoding="utf-8",
    )
    (tmp_path / "evalgate.json").write_text(
        json.dumps(
            {
                "name": "tiny",
                "dataset": "golden.jsonl",
                "system": {"type": "python", "target": "sut:answer"},
                "checks": [{"type": "contains"}, {"type": "grounding"}],
                "gate": {"min_pass_rate": 1.0},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path / "evalgate.json"


class TestConfig:
    def test_missing_file(self):
        with pytest.raises(ConfigError, match="not found"):
            Config.load("nope.yaml")

    def test_missing_keys(self, tmp_path: Path):
        path = tmp_path / "evalgate.json"
        path.write_text(json.dumps({"dataset": "x.jsonl"}), encoding="utf-8")
        with pytest.raises(ConfigError, match="system"):
            Config.load(path)

    def test_rejects_an_impossible_pass_rate(self):
        with pytest.raises(ConfigError):
            Gate.parse({"min_pass_rate": 1.5})


class TestDataset:
    def test_duplicate_ids_are_rejected(self, tmp_path: Path):
        path = tmp_path / "g.jsonl"
        line = json.dumps({"id": "a", "input": {}})
        path.write_text(f"{line}\n{line}\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="duplicate"):
            load_dataset(path)

    def test_bad_json_names_the_line(self, tmp_path: Path):
        path = tmp_path / "g.jsonl"
        path.write_text('{"id": "a", "input": {}}\nnot json\n', encoding="utf-8")
        with pytest.raises(DatasetError, match=":2:"):
            load_dataset(path)


class TestRun:
    def test_scores_each_case(self, suite: Path):
        report = run_suite(Config.load(suite))
        assert report.total == 2
        assert report.passed == 1
        assert report.pass_rate == pytest.approx(0.5)

    def test_check_rates(self, suite: Path):
        rates = run_suite(Config.load(suite)).check_rates()
        assert rates["grounding"] == pytest.approx(1.0)
        assert rates["contains"] == pytest.approx(0.5)

    def test_filtering_by_case_id(self, suite: Path):
        report = run_suite(Config.load(suite), only=["good"])
        assert [c.id for c in report.cases] == ["good"]

    def test_a_crashing_system_fails_its_case_only(self, tmp_path: Path, suite: Path):
        (tmp_path / "sut.py").write_text(
            "def answer(payload):\n    raise RuntimeError('upstream 500')\n", encoding="utf-8"
        )
        import sys

        sys.modules.pop("sut", None)
        report = run_suite(Config.load(suite))
        assert report.passed == 0
        assert all("upstream 500" in (c.error or "") for c in report.cases)


class TestGate:
    def test_fails_below_the_pass_rate(self, suite: Path):
        report = run_suite(Config.load(suite))
        result = evaluate(Gate(min_pass_rate=1.0), report)
        assert not result.passed
        assert "pass rate" in result.reasons[0]

    def test_passes_when_the_bar_is_met(self, suite: Path):
        report = run_suite(Config.load(suite))
        assert evaluate(Gate(min_pass_rate=0.5), report).passed

    def test_per_check_floor(self, suite: Path):
        report = run_suite(Config.load(suite))
        result = evaluate(Gate(min_pass_rate=0.0, per_check={"contains": 0.9}), report)
        assert not result.passed

    def test_unknown_check_in_the_gate_is_a_note_not_a_failure(self, suite: Path):
        report = run_suite(Config.load(suite))
        result = evaluate(Gate(min_pass_rate=0.0, per_check={"judge": 0.9}), report)
        assert result.passed
        assert result.notes


class TestBaseline:
    def test_regression_is_detected(self, suite: Path, tmp_path: Path):
        report = run_suite(Config.load(suite))
        path = save_baseline(tmp_path / "base.json", report)
        stored = load_baseline(path)
        stored["good"]["contains"] = True
        stored["bad"]["contains"] = True  # pretend it used to pass
        delta = compare(report, stored)
        assert ("bad", "contains") in delta.regressions

    def test_a_fix_is_reported_separately(self, suite: Path, tmp_path: Path):
        report = run_suite(Config.load(suite))
        stored = load_baseline(save_baseline(tmp_path / "b.json", report))
        stored["good"]["contains"] = False
        delta = compare(report, stored)
        assert ("good", "contains") in delta.fixes
        assert not delta.regressions

    def test_regressions_fail_the_gate(self, suite: Path, tmp_path: Path):
        report = run_suite(Config.load(suite))
        stored = load_baseline(save_baseline(tmp_path / "b.json", report))
        stored["bad"]["contains"] = True
        delta = compare(report, stored)
        assert not evaluate(Gate(min_pass_rate=0.0, max_regressions=0), report, delta).passed

    def test_missing_baseline_file_is_empty_not_an_error(self, tmp_path: Path):
        assert load_baseline(tmp_path / "absent.json") == {}


class TestReports:
    def test_terminal_names_the_failing_case(self, suite: Path):
        report = run_suite(Config.load(suite))
        text = terminal(report, evaluate(Gate(min_pass_rate=1.0), report))
        assert "bad" in text and "gate: FAILED" in text

    def test_markdown_has_a_table(self, suite: Path):
        report = run_suite(Config.load(suite))
        text = markdown(report, evaluate(Gate(min_pass_rate=0.0), report))
        assert "| check | pass rate |" in text

    def test_junit_is_parseable(self, suite: Path):
        from xml.etree import ElementTree as ET

        report = run_suite(Config.load(suite))
        root = ET.fromstring(junit(report))
        assert root.get("tests") == "2"
        assert root.get("failures") == "1"


class TestCli:
    def test_run_exits_nonzero_when_the_gate_fails(self, suite: Path, capsys):
        assert main(["run", "-c", str(suite)]) == 1
        assert "gate: FAILED" in capsys.readouterr().out

    def test_writes_artifacts(self, suite: Path, tmp_path: Path):
        out = tmp_path / "out"
        main(["run", "-c", str(suite), "--json", str(out / "r.json"), "--junit", str(out / "r.xml")])
        assert json.loads((out / "r.json").read_text(encoding="utf-8"))["run"]["total"] == 2
        assert (out / "r.xml").exists()

    def test_baseline_subcommand(self, suite: Path, tmp_path: Path, capsys):
        assert main(["baseline", "-c", str(suite), "-o", str(tmp_path / "b.json")]) == 0
        assert (tmp_path / "b.json").exists()

    def test_checks_subcommand(self, capsys):
        assert main(["checks"]) == 0
        assert "grounding" in capsys.readouterr().out


class TestExample:
    def test_the_shipped_example_passes_its_own_gate(self):
        report = run_suite(Config.load(EXAMPLE))
        result = evaluate(Config.load(EXAMPLE).gate, report)
        assert result.passed, terminal(report, result)

    def test_the_sloppy_mode_is_caught(self, monkeypatch):
        monkeypatch.setenv("SUPPORT_BOT_SLOPPY", "1")
        config = Config.load(EXAMPLE)
        report = run_suite(config)
        result = evaluate(config.gate, report)
        assert not result.passed
        assert report.check_rates()["grounding"] < 1.0
