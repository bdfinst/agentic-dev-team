"""scripts/run_integration_eval.py's run_commands() used to call
subprocess.run(..., shell=True) with no timeout on each fixture-declared
testCommand (evals/expected/*.json). Fixture specs are trusted, but a hung
command (a test that deadlocks, a server that never exits) would still
block the harness forever. These tests lock existing behavior and then
assert a hard timeout is enforced.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

SCRIPT_PATH = REPO_ROOT / "scripts" / "run_integration_eval.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_integration_eval", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_integration_eval"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


rie = _load_module()


def test_run_commands_records_exit_code_and_stderr_first_line(tmp_path: Path) -> None:
    results = rie.run_commands(tmp_path, ['python3 -c "import sys; sys.exit(0)"'])
    assert results == [
        {
            "command": 'python3 -c "import sys; sys.exit(0)"',
            "exit_code": 0,
            "stderr_first_line": "",
        }
    ]


def test_run_commands_captures_failure_and_stderr(tmp_path: Path) -> None:
    results = rie.run_commands(
        tmp_path,
        ["python3 -c \"import sys; print('boom', file=sys.stderr); sys.exit(1)\""],
    )
    assert results[0]["exit_code"] == 1
    assert results[0]["stderr_first_line"] == "boom"


def test_run_commands_times_out_instead_of_hanging_forever(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RUN_INTEGRATION_EVAL_CMD_TIMEOUT", "1")
    results = rie.run_commands(tmp_path, ['python3 -c "import time; time.sleep(30)"'])
    assert len(results) == 1
    assert results[0]["exit_code"] != 0
    assert "timed out" in results[0]["stderr_first_line"].lower()
