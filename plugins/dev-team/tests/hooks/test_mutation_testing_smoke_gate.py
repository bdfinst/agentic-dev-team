"""Unit tests for hooks/mutation_testing_smoke_gate.py (#565, #574, #572).

These are white-box tests on the port's helpers. Byte-parity with the .sh
sibling is enforced separately by the parity harness (Slice 4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


_HOOKS = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import mutation_testing_smoke_gate as gate  # type: ignore[import-not-found]  # noqa: E402


# --- trigger detection -----------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "dotnet stryker",
        "dotnet stryker --mutate src/Foo.cs",
        "  dotnet   stryker  ",
        "cd repo && dotnet stryker --config-file config.json",
        "bash plugins/dev-team/hooks/mutation-adapters/csharp-stryker-net-wrapper.sh --arg",
        "/abs/path/to/csharp-stryker-net-wrapper.sh",
    ],
)
def test_is_stryker_command_matches_expected(cmd: str) -> None:
    assert gate.is_stryker_command(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "",
        "echo hi",
        "dotnet build",
        "dotnetstryker",  # no boundary
        "pip install stryker",
    ],
)
def test_is_stryker_command_ignores_non_stryker(cmd: str) -> None:
    assert gate.is_stryker_command(cmd) is False


# --- --mutate extraction ---------------------------------------------------


@pytest.mark.parametrize(
    "cmd,expected",
    [
        ("dotnet stryker --mutate src/Foo.cs", "src/Foo.cs"),
        ("dotnet stryker --mutate=src/Foo.cs", "src/Foo.cs"),
        ("dotnet stryker -m src/Foo.cs", "src/Foo.cs"),
        ("dotnet stryker --mutate 'src/Has Space.cs'", "src/Has Space.cs"),
        ('dotnet stryker --mutate "src/Foo.cs"', "src/Foo.cs"),
        ("dotnet stryker", ""),
        ("dotnet stryker --mutate", ""),  # missing value
    ],
)
def test_extract_mutate_value(cmd: str, expected: str) -> None:
    assert gate.extract_mutate_value(cmd) == expected


def test_extract_mutate_value_on_malformed_shell_returns_empty() -> None:
    # An unclosed quote breaks shlex → return empty (silent), matching the .sh.
    assert gate.extract_mutate_value("dotnet stryker --mutate 'unclosed") == ""


# --- single-file classification -------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("src/Foo.cs", True),
        ("", False),
        ("src/*.cs", False),  # glob
        ("src/?oo.cs", False),  # glob
        ("src/[Ff]oo.cs", False),  # glob
        ("src/Foo.cs;src/Bar.cs", False),  # semi-colon multi
    ],
)
def test_is_single_file_mutate(value: str, expected: bool) -> None:
    assert gate.is_single_file_mutate(value) is expected


# --- audit-log helpers -----------------------------------------------------


def test_sha256_first_16_is_deterministic() -> None:
    assert gate.sha256_first_16("hello") == gate.sha256_first_16("hello")
    assert len(gate.sha256_first_16("hello")) == 16


def test_iso_utc_timestamp_z_suffix() -> None:
    ts = gate.iso_utc_timestamp()
    assert ts.endswith("Z")
    assert "T" in ts


def test_log_bypass_audit_writes_hashed_jsonl(tmp_path: Path) -> None:
    cwd = tmp_path
    gate.log_bypass_audit("dotnet stryker --whole-scope", str(cwd))
    audit = cwd / "metrics" / "gate-bypass.jsonl"
    assert audit.is_file()
    lines = audit.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["hook"] == "mutation-testing-smoke-gate"
    assert record["cwd"] == str(cwd)
    assert record["timestamp"].endswith("Z")
    # command hash, never the raw command
    assert "stryker" not in record["command_hash"]
    assert len(record["command_hash"]) == 16


# --- main() dispatch -------------------------------------------------------


def _run_main(monkeypatch, stdin_str: str, env: dict) -> tuple[int, str]:
    monkeypatch.setattr(sys, "stdin", _make_stdin(stdin_str))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from io import StringIO

    buf = StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = gate.main()
    return rc, buf.getvalue()


def _make_stdin(text: str):
    from io import StringIO

    return StringIO(text)


def test_main_silent_pass_on_empty_stdin(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    rc, out = _run_main(monkeypatch, "", {})
    assert rc == 0
    assert out == ""


def test_main_silent_pass_on_non_stryker_command(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 0
    assert out == ""


def test_main_silent_pass_on_single_file_mutate(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = json.dumps(
        {"tool_input": {"command": "dotnet stryker --mutate src/Foo.cs"}}
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 0
    assert out == ""


def test_main_blocks_when_no_smoke_report(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 2
    assert "[BLOCK]" in out
    assert "no smoke report" in out
    assert "Step 1c" in out


def test_main_passes_when_smoke_report_has_killed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reports = tmp_path / "StrykerOutput" / "smoke" / "reports"
    reports.mkdir(parents=True)
    (reports / "mutation-report.json").write_text(
        json.dumps({"mutants": [{"status": "Killed"}, {"status": "Survived"}]})
    )
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 0
    assert out == ""


def test_main_blocks_when_killed_zero_survived_nonzero(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    reports = tmp_path / "StrykerOutput" / "smoke" / "reports"
    reports.mkdir(parents=True)
    (reports / "mutation-report.json").write_text(
        json.dumps({"mutants": [{"status": "Survived"}, {"status": "Survived"}]})
    )
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 2
    assert "[BLOCK]" in out
    assert "killed=0" in out


def test_main_blocks_on_empty_or_uncovered_mutants(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reports = tmp_path / "StrykerOutput" / "smoke" / "reports"
    reports.mkdir(parents=True)
    (reports / "mutation-report.json").write_text(
        json.dumps({"mutants": [{"status": "NoCoverage"}]})
    )
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 2
    assert "no scored mutants" in out


def test_main_advisory_on_malformed_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reports = tmp_path / "StrykerOutput" / "smoke" / "reports"
    reports.mkdir(parents=True)
    (reports / "mutation-report.json").write_text("{not valid json")
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 0
    assert out.startswith("ADVISORY:")
    assert "not valid JSON" in out


def test_main_advisory_on_missing_mutants_key(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reports = tmp_path / "StrykerOutput" / "smoke" / "reports"
    reports.mkdir(parents=True)
    (reports / "mutation-report.json").write_text(json.dumps({"other": "shape"}))
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 0
    assert "lacks the mutants[] key" in out
    assert out.startswith("ADVISORY:")


def test_main_escape_hatch_bypasses_and_audits(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = json.dumps(
        {
            "tool_input": {"command": "dotnet stryker --config-file c.json"},
            "cwd": str(tmp_path),
        }
    )
    rc, out = _run_main(monkeypatch, payload, {"MUTATION_SMOKE_GATE_SKIP": "1"})
    assert rc == 0
    assert out == ""
    audit = tmp_path / "metrics" / "gate-bypass.jsonl"
    assert audit.is_file()


def test_main_advisory_on_missing_jq(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        gate.shutil, "which", lambda name: None if name == "jq" else "/usr/bin/" + name
    )
    payload = json.dumps({"tool_input": {"command": "dotnet stryker"}})
    rc, out = _run_main(monkeypatch, payload, {})
    assert rc == 0
    assert out.startswith("ADVISORY:")
    assert "jq is required" in out
