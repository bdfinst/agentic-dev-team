"""Unit tests for hooks/mutation_gate.py (#588 / #572 Phase 2 D1).

Focus on the hook's dispatch logic — the branches that decide whether to
invoke an adapter. The adapter-level behaviours are covered in
`tests/hooks/test_mutation_adapters_lib.py` (Cluster D unit tests).
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import mutation_gate


def _feed(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


_ADAPTER_ENV_KEYS = (
    "ADAPTER_TIMEOUT",
    "ADAPTER_COMMAND",
    "ADAPTER_RUNNER_STDOUT",
    "ADAPTER_SOURCE_FILE",
)


@pytest.fixture(autouse=True)
def _hermetic_tmpdir(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MUTATION_GATE_SKIP", raising=False)
    monkeypatch.delenv("MUTATION_GATE_TIMEOUT", raising=False)
    yield
    # mutation_gate.main() sets ADAPTER_* via plain `os.environ[...] = ...`
    # (real config for a real subprocess adapter, not monkeypatch.setenv) —
    # monkeypatch.delenv(key, raising=False) called *before* the test is a
    # no-op when the key is absent at that point (MonkeyPatch.delitem only
    # records an undo entry when the key currently exists; raising=False on a
    # missing key just returns without appending to the undo stack), so it
    # cannot pre-register cleanup for a key main() is about to create.
    # Without this explicit teardown, running this file leaks
    # ADAPTER_TIMEOUT=60 into the real process environment for every test
    # that runs afterward in the same (possibly xdist-parallel) worker —
    # observed corrupting test_mutmut_adapter.py's default-timeout
    # assertions under CI's worker grouping (#1359's PR CI failure; this
    # file's own local run never surfaced it since nothing after it in the
    # same file depends on these defaults).
    for key in _ADAPTER_ENV_KEYS:
        os.environ.pop(key, None)


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


# ---------------------------------------------------------------------------
# Dependency guard + emit helpers
# ---------------------------------------------------------------------------


def test_jq_missing_emits_exact_advisory(monkeypatch, capsys):
    monkeypatch.setattr(mutation_gate.shutil, "which", lambda name: None)
    _feed(monkeypatch, '{"tool_input":{"command":"npm test"}}')
    assert mutation_gate.main() == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert "jq is required but not installed" in ctx
    assert "brew install jq" in ctx
    assert "apt install jq" in ctx
    assert "winget install jqlang.jq" in ctx
    assert "/setup" in ctx


def test_jq_guard_checks_for_jq(monkeypatch, capsys):
    # Prove the guard probes specifically for "jq", not some other binary.
    probed = []
    monkeypatch.setattr(
        mutation_gate.shutil, "which", lambda name: probed.append(name) or None
    )
    _feed(monkeypatch, '{"tool_input":{"command":"npm test"}}')
    assert mutation_gate.main() == 0
    assert "jq" in probed


def test_emit_advisory_pretty_structure_and_indent(capsys):
    mutation_gate._emit_advisory_pretty("hello world")
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert payload["hookSpecificOutput"]["additionalContext"] == "hello world"
    # indent=2 produces a two-space-indented key.
    assert '\n  "hookSpecificOutput"' in out


def test_emit_block_pretty_structure_and_indent(capsys):
    mutation_gate._emit_block_pretty("because reasons")
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["decision"] == "block"
    assert payload["reason"] == "because reasons"
    assert '\n  "decision"' in out


def test_main_returns_zero_on_non_dict_payload(monkeypatch):
    _feed(monkeypatch, "[1, 2, 3]")
    assert mutation_gate.main() == 0


def test_no_adapter_advisory_names_supported_tools(monkeypatch, capsys):
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
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert "Run /setup to install one" in ctx
    assert "Stryker" in ctx
    assert "pitest" in ctx
    assert "Stryker.NET" in ctx


# ---------------------------------------------------------------------------
# Skip env short-circuits BEFORE any dispatch
# ---------------------------------------------------------------------------


def test_skip_env_suppresses_dispatch(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )
    # A dispatch would emit a block if reached; the skip must prevent it.
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)
    monkeypatch.setattr(
        mutation_gate.stryker,
        "stryker_run",
        lambda path: (Path(path).write_text(json.dumps([{"name": "t"}])), 0)[1],
    )
    monkeypatch.setenv("MUTATION_GATE_SKIP", "1")
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
    assert "decision" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Block boundary-event arguments
# ---------------------------------------------------------------------------


def test_block_emits_boundary_event_with_expected_args(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)

    def fake_run(path):
        Path(path).write_text(json.dumps([{"name": "flakyTest"}]))
        return 0

    monkeypatch.setattr(mutation_gate.stryker, "stryker_run", fake_run)

    events = []
    monkeypatch.setattr(
        mutation_gate, "emit_boundary_event", lambda *a, **k: events.append(a)
    )
    _feed(
        monkeypatch,
        json.dumps(
            {
                "tool_input": {"command": "npm test"},
                "tool_response": {"exit_code": 0, "output": "5 passing"},
                "cwd": "/wd",
                "session_id": "sess-9",
            }
        ),
    )
    assert mutation_gate.main() == 0
    assert events == [
        ("/wd", "mutation_gate", "Bash", "block", "mutation-gate-zero-kills", "sess-9")
    ]


# ---------------------------------------------------------------------------
# Stryker source-file derivation into ADAPTER_SOURCE_FILE
# ---------------------------------------------------------------------------


def test_stryker_dispatch_sets_source_file_env_from_last_arg(monkeypatch):
    from mutation_adapters import lib as adapter_lib

    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)

    captured = {}

    def fake_run(path):
        captured["source_file"] = os.environ.get("ADAPTER_SOURCE_FILE")
        Path(path).write_text("[]")
        return 0

    monkeypatch.setattr(mutation_gate.stryker, "stryker_run", fake_run)
    _feed(
        monkeypatch,
        json.dumps(
            {
                "tool_input": {"command": "npm test src/calc.test.ts"},
                "tool_response": {"exit_code": 0, "output": "ok"},
            }
        ),
    )
    assert mutation_gate.main() == 0
    # last arg "src/calc.test.ts" -> derive_source_file -> "src/calc.ts".
    assert captured["source_file"] == "src/calc.ts"


# ---------------------------------------------------------------------------
# Adapter dispatch branches (pitest / stryker-net / mutmut)
# ---------------------------------------------------------------------------


def _seed_red(adapter_lib):
    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "1 failing"}}),
    )


def _green(command):
    return json.dumps(
        {
            "tool_input": {"command": command},
            "tool_response": {"exit_code": 0, "output": "ok"},
        }
    )


def test_pitest_dispatch_returns_zero_when_undetected(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.pitest, "pitest_detect", lambda: False)
    ran = []
    monkeypatch.setattr(
        mutation_gate.pitest, "pitest_run", lambda path: ran.append(path)
    )
    _feed(monkeypatch, _green("mvn test"))
    assert mutation_gate.main() == 0
    assert ran == []  # undetected -> never runs
    assert "decision" not in capsys.readouterr().out


def test_pitest_dispatch_emits_block_on_zero_kills(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.pitest, "pitest_detect", lambda: True)
    monkeypatch.setattr(
        mutation_gate.pitest,
        "pitest_run",
        lambda path: Path(path).write_text(json.dumps([{"name": "weakTest"}])),
    )
    _feed(monkeypatch, _green("mvn test"))
    assert mutation_gate.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_stryker_net_dispatch_emits_block_on_zero_kills(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(
        mutation_gate.stryker_net, "stryker_net_detect", lambda: True
    )
    monkeypatch.setattr(
        mutation_gate.stryker_net,
        "stryker_net_run",
        lambda path: Path(path).write_text(json.dumps([{"name": "weakTest"}])),
    )
    _feed(monkeypatch, _green("dotnet test"))
    assert mutation_gate.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_mutmut_dispatch_emits_block_on_zero_kills(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.mutmut, "mutmut_detect", lambda: True)
    monkeypatch.setattr(
        mutation_gate.mutmut,
        "mutmut_run",
        lambda path: Path(path).write_text(json.dumps([{"name": "weakTest"}])),
    )
    _feed(monkeypatch, _green("pytest"))
    assert mutation_gate.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_mutmut_dispatch_returns_zero_when_undetected(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.mutmut, "mutmut_detect", lambda: False)
    ran = []
    monkeypatch.setattr(
        mutation_gate.mutmut, "mutmut_run", lambda path: ran.append(path)
    )
    _feed(monkeypatch, _green("pytest"))
    assert mutation_gate.main() == 0
    assert ran == []
    assert "decision" not in capsys.readouterr().out


def test_stryker_dispatch_returns_zero_when_undetected(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: False)
    ran = []
    monkeypatch.setattr(
        mutation_gate.stryker, "stryker_run", lambda path: ran.append(path)
    )
    _feed(monkeypatch, _green("npm test"))
    assert mutation_gate.main() == 0
    assert ran == []
    assert "decision" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Exact advisory text (kills token-level string mutants in the messages)
# ---------------------------------------------------------------------------


def test_jq_missing_advisory_is_verbatim(monkeypatch, capsys):
    monkeypatch.setattr(mutation_gate.shutil, "which", lambda name: None)
    _feed(monkeypatch, '{"tool_input":{"command":"npm test"}}')
    assert mutation_gate.main() == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert ctx == (
        "MUTATION GATE ADVISORY: jq is required but not installed. Run "
        "/setup to install it, or: brew install jq (macOS) / apt install jq "
        "(Linux) / winget install jqlang.jq (Windows)."
    )


def test_no_adapter_advisory_is_verbatim(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    _feed(monkeypatch, _green("go test ./..."))
    assert mutation_gate.main() == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert ctx == (
        "MUTATION GATE ADVISORY: no mutation testing adapter for this "
        "language. Run /setup to install one (supports JS/TS via "
        "Stryker, Java via pitest, C# via Stryker.NET)."
    )


# ---------------------------------------------------------------------------
# ADAPTER_* environment configured for the subprocess adapter
# ---------------------------------------------------------------------------


def test_dispatch_configures_adapter_environment(monkeypatch):
    from mutation_adapters import lib as adapter_lib

    # Seed a prior RED state whose runner output must flow into the adapter.
    adapter_lib.write_state(
        "fail",
        json.dumps({"tool_response": {"exit_code": 1, "output": "PRIOR RED OUTPUT"}}),
    )
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)

    captured = {}

    def fake_run(path):
        captured["timeout"] = os.environ.get("ADAPTER_TIMEOUT")
        captured["command"] = os.environ.get("ADAPTER_COMMAND")
        captured["runner_stdout"] = os.environ.get("ADAPTER_RUNNER_STDOUT")
        Path(path).write_text("[]")
        return 0

    monkeypatch.setattr(mutation_gate.stryker, "stryker_run", fake_run)
    _feed(monkeypatch, _green("npm test"))
    assert mutation_gate.main() == 0
    assert captured["timeout"] == "60"
    assert captured["command"] == "npm test"
    assert captured["runner_stdout"] == "PRIOR RED OUTPUT"


def test_adapter_timeout_env_overrides_default(monkeypatch):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setenv("MUTATION_GATE_TIMEOUT", "30")
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)

    captured = {}

    def fake_run(path):
        captured["timeout"] = os.environ.get("ADAPTER_TIMEOUT")
        Path(path).write_text("[]")
        return 0

    monkeypatch.setattr(mutation_gate.stryker, "stryker_run", fake_run)
    _feed(monkeypatch, _green("npm test"))
    assert mutation_gate.main() == 0
    assert captured["timeout"] == "30"


# ---------------------------------------------------------------------------
# Block edge cases — invalid zero-kills JSON, cwd default
# ---------------------------------------------------------------------------


def test_invalid_zero_kills_json_emits_no_block(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)
    monkeypatch.setattr(
        mutation_gate.stryker,
        "stryker_run",
        lambda path: Path(path).write_text("{ not valid json"),
    )
    _feed(monkeypatch, _green("npm test"))
    assert mutation_gate.main() == 0
    assert "decision" not in capsys.readouterr().out


def test_block_boundary_event_defaults_cwd_to_dot(monkeypatch, capsys):
    from mutation_adapters import lib as adapter_lib

    _seed_red(adapter_lib)
    monkeypatch.setattr(mutation_gate.stryker, "stryker_detect", lambda: True)
    monkeypatch.setattr(
        mutation_gate.stryker,
        "stryker_run",
        lambda path: Path(path).write_text(json.dumps([{"name": "weakTest"}])),
    )
    events = []
    monkeypatch.setattr(
        mutation_gate, "emit_boundary_event", lambda *a, **k: events.append(a)
    )
    # No cwd / session_id in the payload.
    _feed(monkeypatch, _green("npm test"))
    assert mutation_gate.main() == 0
    assert events[0][0] == "."
    assert events[0][5] is None
