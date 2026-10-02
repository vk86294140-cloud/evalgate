from __future__ import annotations

import sys
from pathlib import Path

import pytest

from evalgate.adapters import AdapterError, build_adapter
from evalgate.config import SystemSpec


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


class TestPythonAdapter:
    def test_calls_the_target(self, tmp_path: Path):
        write(tmp_path, "sut.py", "def answer(p):\n    return {'echo': p['q']}\n")
        adapter = build_adapter(SystemSpec("python", "sut:answer"), tmp_path)
        assert adapter({"q": "hi"}) == {"echo": "hi"}

    def test_two_suites_can_both_define_system_py(self, tmp_path: Path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir()
        b.mkdir()
        write(a, "system.py", "def answer(p):\n    return {'from': 'a'}\n")
        write(b, "system.py", "def answer(p):\n    return {'from': 'b'}\n")
        first = build_adapter(SystemSpec("python", "system:answer"), a)
        second = build_adapter(SystemSpec("python", "system:answer"), b)
        assert first({}) == {"from": "a"}
        assert second({}) == {"from": "b"}

    def test_a_target_without_a_colon_is_rejected(self, tmp_path: Path):
        with pytest.raises(AdapterError, match="module:callable"):
            build_adapter(SystemSpec("python", "sut"), tmp_path)

    def test_a_missing_module_is_reported(self, tmp_path: Path):
        with pytest.raises(AdapterError, match="cannot import"):
            build_adapter(SystemSpec("python", "nowhere_at_all:answer"), tmp_path)

    def test_a_non_callable_attribute_is_rejected(self, tmp_path: Path):
        write(tmp_path, "sut.py", "answer = 42\n")
        with pytest.raises(AdapterError, match="not callable"):
            build_adapter(SystemSpec("python", "sut:answer"), tmp_path)

    def test_a_non_dict_return_is_rejected(self, tmp_path: Path):
        write(tmp_path, "sut.py", "def answer(p):\n    return 'just a string'\n")
        adapter = build_adapter(SystemSpec("python", "sut:answer"), tmp_path)
        with pytest.raises(AdapterError, match="expected a dict"):
            adapter({})

    def test_an_import_time_error_is_reported(self, tmp_path: Path):
        write(tmp_path, "sut.py", "raise ValueError('bad config at import')\n")
        with pytest.raises(AdapterError, match="bad config at import"):
            build_adapter(SystemSpec("python", "sut:answer"), tmp_path)


class TestCommandAdapter:
    def test_round_trips_json_over_stdio(self, tmp_path: Path):
        write(
            tmp_path,
            "sut_cli.py",
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'echo': payload['q']}))\n",
        )
        spec = SystemSpec("command", f'"{sys.executable}" sut_cli.py')
        assert build_adapter(spec, tmp_path)({"q": "hello"}) == {"echo": "hello"}

    def test_a_nonzero_exit_is_reported(self, tmp_path: Path):
        write(tmp_path, "boom.py", "import sys\nsys.stderr.write('upstream died')\nsys.exit(3)\n")
        spec = SystemSpec("command", f'"{sys.executable}" boom.py')
        with pytest.raises(AdapterError, match="exited 3"):
            build_adapter(spec, tmp_path)({})

    def test_non_json_stdout_is_reported(self, tmp_path: Path):
        write(tmp_path, "chatty.py", "print('I am not JSON')\n")
        spec = SystemSpec("command", f'"{sys.executable}" chatty.py')
        with pytest.raises(AdapterError, match="not JSON"):
            build_adapter(spec, tmp_path)({})

    def test_a_json_scalar_is_not_an_object(self, tmp_path: Path):
        write(tmp_path, "scalar.py", "print('42')\n")
        spec = SystemSpec("command", f'"{sys.executable}" scalar.py')
        with pytest.raises(AdapterError, match="JSON object"):
            build_adapter(spec, tmp_path)({})

    def test_a_hanging_command_times_out(self, tmp_path: Path):
        write(tmp_path, "slow.py", "import time\ntime.sleep(30)\n")
        spec = SystemSpec("command", f'"{sys.executable}" slow.py', timeout_s=1.0)
        with pytest.raises(AdapterError, match="timed out"):
            build_adapter(spec, tmp_path)({})
