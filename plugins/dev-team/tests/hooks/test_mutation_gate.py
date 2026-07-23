"""Unit tests for hooks/mutation_gate.py (#588 / #572 Phase 2 D1).

Focus on the hook's dispatch logic — the branches that decide whether to
invoke an adapter. The adapter-level behaviours are covered in
`tests/hooks/test_mutation_adapters_lib.py` (Cluster D unit tests).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import mutation_gate  # noqa: E402


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


@pytest.fixture(autouse=True)
def _hermetic_tmpdir(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MUTATION_GATE_SKIP", raising=False)
    monkeypatch.delenv("MUTATION_GATE_TIMEOUT", raising=False)


def test_main_returns_zero_on_empty_stdin(monkeypatch):
    _feed(monkeypatch, "")
    assert mutation_gate.main() == 0


def test_main_returns_zero_on_malformed_stdin(monkeypatch):
    _feed(monkeypatch, "not-json")
    assert mutation_gate.main() == 0


def test_main_returns_zero_when_command_missing(monkeypatch):
    _feed(monkeypatch, "{}")
    assert mutation_gate.main() == 0


def test_main_returns_zero_when_skip_env(monkeypatch):
    monkeypatch.setenv("MUTATION_GATE_SKIP", "1")
    _feed(monkeypatch, '{"tool_input":{"command":"npm test"}}')
    assert mutation_gate.main() == 0


def test_main_returns_zero_on_non_test_command(monkeypatch):
    _feed(monkeypatch, '{"tool_input":{"command":"npm run build"}}')
    assert mutation_gate.main() == 0


def test_main_records_result_but_no_transition_on_first_red(monkeypatch, tmp_path):
    # No prior state — a fail on first touch cannot be a RED→GREEN transition.
    payload = json.dumps(
        {
            "tool_input": {"command": "npm test"},
            "tool_response": {"exit_code": 1, "output": "1 failing"},
        }
    )
    _feed(monkeypatch, payload)
    assert mutation_gate.main() == 0
    # State file created under the mocked TMPDIR.
    state_files = list((tmp_path / "mutation-gate").glob("session-*"))
    assert state_files, "expected a state file to be recorded"
    payload = json.loads(state_files[0].read_text())
    assert payload["result"] == "fail"


def test_main_transitions_dispatches_and_emits_no_block_when_zero_kills_empty(
    monkeypatch, tmp_path, capsys
):
    from mutation_adapters import lib as adapter_lib

    # Seed a prior RED state so this run is a RED→GREEN transition.
    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )

    # Stub the adapter dispatch — pretend Stryker was detected but produced
    # an empty zero-kill list (all mutants killed). No block should emit.
    def fake_detect():
        return True

    def fake_run(output_path):
        Path(output_path).write_text("[]")
        return 0

    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", fake_detect)
    monkeypatch.setattr(mutation_gate.stryker, "stryker_run", fake_run)

    _feed(
        monkeypatch,
        json.dumps(
            {
                "tool_input": {"command": "npm test"},
                "tool_response": {"exit_code": 0, "output": "5 passing"},
            }
        ),
    )
    assert mutation_gate.main() == 0
    out = capsys.readouterr().out
    assert "decision" not in out  # no block emitted


def test_main_emits_block_when_zero_kills_present(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )

    def fake_detect():
        return True

    def fake_run(output_path):
        Path(output_path).write_text(
            json.dumps(
                [
                    {
                        "name": "flakyTest",
                        "file": "src/calc.ts",
                        "line": 10,
                        "covered": 3,
                    }
                ]
            )
        )
        return 0

    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", fake_detect)
    monkeypatch.setattr(mutation_gate.stryker, "stryker_run", fake_run)

    _feed(
        monkeypatch,
        json.dumps(
            {
                "tool_input": {"command": "npm test"},
                "tool_response": {"exit_code": 0, "output": "5 passing"},
            }
        ),
    )
    assert mutation_gate.main() == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["decision"] == "block"
    assert "MUTATION GATE BLOCKED" in payload["reason"]
    assert "flakyTest" in payload["reason"]


def test_main_emits_no_adapter_advisory(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )
    _feed(
        monkeypatch,
        json.dumps(
            {
                "tool_input": {"command": "go test ./..."},
                "tool_response": {"exit_code": 0, "output": "ok"},
            }
        ),
    )
    assert mutation_gate.main() == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert (
        "no mutation testing adapter"
        in payload["hookSpecificOutput"]["additionalContext"]
    )
