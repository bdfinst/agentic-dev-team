"""Unit tests for hooks/mutation_adapters/lib.py — #578 (Cluster D shared lib).

Byte-parity with the bash lib for the entry points mutation-gate.sh relies on:
- detect_adapter / is_test_command / detect_result / is_red_to_green
- emit_block / emit_advisory (JSON envelope shape)
- write_state / read_state (session TTL + purge)
- parse_stryker_kills (Stryker JSON → zero-kill list)
- format_blocking_reason (human-readable reason text)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from mutation_adapters import lib  # noqa: E402


# ---------------------------------------------------------------------------
# JSON emit helpers
# ---------------------------------------------------------------------------


def test_emit_block_returns_expected_json():
    result = lib.emit_block("zero-kill detected")
    payload = json.loads(result)
    assert payload == {"decision": "block", "reason": "zero-kill detected"}


def test_emit_advisory_wraps_in_posttooluse_envelope():
    result = lib.emit_advisory("timed out")
    payload = json.loads(result)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert payload["hookSpecificOutput"]["additionalContext"] == "timed out"


# ---------------------------------------------------------------------------
# is_test_command / detect_adapter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd,expected",
    [
        ("npm test", True),
        ("npm run test", True),
        ("npm run test --coverage", True),
        ("npm run build", False),
        ("npx vitest run", True),
        ("npx jest --ci", True),
        ("mvn test", True),
        ("mvn verify", True),
        ("./mvnw test", True),
        ("gradle test", True),
        ("./gradlew test", True),
        ("dotnet test", True),
        ("dotnet build", False),
        ("pytest tests/", True),
        ("python -m pytest tests/", True),
        ("python3 -m pytest", True),
        ("go test ./...", True),
        ("cargo test", True),
        ("echo hi", False),
        ("", False),
    ],
)
def test_is_test_command(cmd, expected):
    assert lib.is_test_command(cmd) is expected


@pytest.mark.parametrize(
    "cmd,expected",
    [
        ("npm test", "stryker"),
        ("npm run test", "stryker"),
        ("npx vitest run", "stryker"),
        ("npx jest --ci", "stryker"),
        ("mvn test", "pitest"),
        ("mvn verify", "pitest"),
        ("./mvnw test", "pitest"),
        ("gradle test", "pitest"),
        ("./gradlew test", "pitest"),
        ("dotnet test", "stryker-net"),
        ("pytest", "mutmut"),
        ("python -m pytest tests/", "mutmut"),
        ("python3 -m pytest", "mutmut"),
        ("python3 -m unittest discover", "mutmut"),
        ("go test ./...", "none"),
        ("echo hi", "none"),
    ],
)
def test_detect_adapter(cmd, expected):
    assert lib.detect_adapter(cmd) == expected


# ---------------------------------------------------------------------------
# detect_result / is_red_to_green
# ---------------------------------------------------------------------------


def _event_json(exit_code=None, output=""):
    body = {"tool_response": {"output": output}}
    if exit_code is not None:
        body["tool_response"]["exit_code"] = exit_code
    return json.dumps(body)


def test_detect_result_exit_zero_is_pass():
    assert lib.detect_result(_event_json(exit_code=0)) == "pass"


def test_detect_result_exit_nonzero_is_fail():
    assert lib.detect_result(_event_json(exit_code=1)) == "fail"


def test_detect_result_stdout_pass_pattern():
    body = _event_json(output="5 passing")
    # No exit code — falls through to output patterns.
    assert lib.detect_result(body) == "pass"


def test_detect_result_stdout_fail_pattern():
    body = _event_json(output="1 failing")
    assert lib.detect_result(body) == "fail"


def test_detect_result_uncertain_defaults_to_fail():
    assert lib.detect_result(_event_json(output="nothing interesting")) == "fail"


def test_detect_result_malformed_stdin_is_fail():
    assert lib.detect_result("not-json") == "fail"


def test_is_red_to_green_transitions():
    assert lib.is_red_to_green("fail", "pass") is True
    assert lib.is_red_to_green("pass", "pass") is False
    assert lib.is_red_to_green("fail", "fail") is False
    assert lib.is_red_to_green("pass", "fail") is False


# ---------------------------------------------------------------------------
# State file management
# ---------------------------------------------------------------------------


@pytest.fixture
def hermetic_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_write_read_state_roundtrip(hermetic_state):
    event = _event_json(exit_code=0, output="all good")
    lib.write_state("pass", event)
    raw = lib.read_state()
    payload = json.loads(raw)
    assert payload["result"] == "pass"
    assert payload["runner_stdout"] == "all good"


def test_state_file_path_stable_across_calls(hermetic_state):
    assert lib.state_file_path() == lib.state_file_path()


def test_state_file_hashes_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    a = lib.state_file_path()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    b = lib.state_file_path()
    assert a != b


def test_read_state_returns_empty_when_absent(hermetic_state):
    assert lib.read_state() == ""


def test_read_state_purges_stale_entry(hermetic_state):
    event = _event_json(exit_code=1, output="oops")
    lib.write_state("fail", event)
    path = lib.state_file_path()
    # Rewrite with a stale timestamp.
    data = json.loads(path.read_text())
    data["timestamp"] = int(time.time()) - 20000
    path.write_text(json.dumps(data))
    assert lib.read_state() == ""
    assert not path.exists()


def test_write_state_truncates_runner_stdout(hermetic_state):
    huge = "x" * (65536 + 1000)
    lib.write_state("pass", _event_json(exit_code=0, output=huge))
    payload = json.loads(lib.read_state())
    assert len(payload["runner_stdout"]) == 65536


# ---------------------------------------------------------------------------
# parse_stryker_kills — read the same fixtures the bash tests use
# ---------------------------------------------------------------------------


_STRYKER_FIXTURES = _REPO_ROOT / "tests" / "hooks" / "fixtures" / "stryker"
_STRYKER_NET_FIXTURES = _REPO_ROOT / "tests" / "hooks" / "fixtures" / "stryker-net"


def test_parse_stryker_kills_zero_kill_fixture(tmp_path):
    output = tmp_path / "zero-kills.json"
    advisory = lib.parse_stryker_kills(
        _STRYKER_FIXTURES / "mutation-zero-kill.json", output
    )
    assert advisory is None
    data = json.loads(output.read_text())
    names = [item["name"] for item in data]
    assert names == ["test-C"]
    # test-C appears in coveredBy of two mutants (1 and 4).
    assert data[0]["covered"] == 2


def test_parse_stryker_kills_all_killed_fixture(tmp_path):
    output = tmp_path / "zero-kills.json"
    lib.parse_stryker_kills(_STRYKER_FIXTURES / "mutation-all-killed.json", output)
    assert json.loads(output.read_text()) == []


def test_parse_stryker_kills_missing_report_emits_advisory(tmp_path):
    output = tmp_path / "zero-kills.json"
    advisory = lib.parse_stryker_kills(tmp_path / "does-not-exist.json", output)
    assert advisory is not None
    payload = json.loads(advisory)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "Stryker report not found" in ctx
    assert output.read_text() == "[]"


def test_parse_stryker_kills_dotnet_fixture(tmp_path):
    output = tmp_path / "zero-kills.json"
    lib.parse_stryker_kills(
        _STRYKER_NET_FIXTURES / "mutation-report-zero-kill.json", output
    )
    data = json.loads(output.read_text())
    assert any(item["name"] == "CalculatorTests.TestDefault" for item in data)


# ---------------------------------------------------------------------------
# format_blocking_reason
# ---------------------------------------------------------------------------


def test_format_blocking_reason_labels_zero_kills(tmp_path):
    payload = [
        {"name": "testA", "file": "src/calc.ts", "line": 10, "covered": 3},
        {"name": "testB", "file": None, "line": None, "covered": 0},
    ]
    zk = tmp_path / "zk.json"
    zk.write_text(json.dumps(payload))
    reason = lib.format_blocking_reason(zk, "npm test")
    assert "MUTATION GATE BLOCKED" in reason
    assert "testA  (src/calc.ts:10)" in reason
    assert "testB  (<unknown>:<unknown>)" in reason
    assert "Covered 3 mutants, killed 0" in reason
    assert reason.endswith("Fix these tests before continuing.")


# ---------------------------------------------------------------------------
# run_with_timeout
# ---------------------------------------------------------------------------


def test_run_with_timeout_exits_124_when_deadline_hits(tmp_path):
    # Use `sh -c` to spawn a portable sleep loop; keep the deadline tiny.
    completed = lib.run_with_timeout(1, ["sh", "-c", "sleep 5"])
    assert completed.returncode == 124


def test_run_with_timeout_passes_through_exit_code():
    completed = lib.run_with_timeout(5, ["sh", "-c", "exit 3"])
    assert completed.returncode == 3


# ---------------------------------------------------------------------------
# detect_coverage_capture_failure (#1156)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "[13:20:25 ERR] It looks like the test coverage capture failed. Disable coverage based optimisation.",
        "it looks like the TEST COVERAGE CAPTURE FAILED.",
        "Disable Coverage Based Optimisation.",
        "noise\nmore noise\n[ERR] test coverage capture failed\n",
    ],
)
def test_detect_coverage_capture_failure_positive(text: str) -> None:
    assert lib.detect_coverage_capture_failure(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Killed:     42\nThe final mutation score is 84.00 %",
        "coverage analysis: perTest",
    ],
)
def test_detect_coverage_capture_failure_negative(text: str) -> None:
    assert lib.detect_coverage_capture_failure(text) is False


# ---------------------------------------------------------------------------
# run_with_timeout — binary selection + fallback synthesis (mutation-kill #1354)
#
# These pin the exact argv/binary chosen when a coreutils `timeout`/`gtimeout`
# is present, and the exact CompletedProcess the pure-Python fallback synthesises
# when neither is on PATH. shutil / subprocess are reached through `lib` so no
# new module import is needed.
# ---------------------------------------------------------------------------


def test_run_with_timeout_prefixes_timeout_binary_when_present(monkeypatch):
    calls = {}

    def fake_which(name):
        return "/bin/timeout" if name == "timeout" else None

    def fake_run(argv, **_kwargs):
        calls["argv"] = argv
        return lib.subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(lib.shutil, "which", fake_which)
    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    lib.run_with_timeout(7, ["echo", "hi"])
    assert calls["argv"] == ["/bin/timeout", "7", "echo", "hi"]


def test_run_with_timeout_uses_gtimeout_when_only_gtimeout_present(monkeypatch):
    calls = {}

    def fake_which(name):
        return "/usr/local/bin/gtimeout" if name == "gtimeout" else None

    def fake_run(argv, **_kwargs):
        calls["argv"] = argv
        return lib.subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(lib.shutil, "which", fake_which)
    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    lib.run_with_timeout(3, ["sleep", "1"])
    assert calls["argv"] == ["/usr/local/bin/gtimeout", "3", "sleep", "1"]


def test_run_with_timeout_fallback_synthesises_124_and_empty_streams(monkeypatch, capsys):
    # No coreutils timeout available → pure-Python fallback path.
    monkeypatch.setattr(lib.shutil, "which", lambda _name: None)
    completed = lib.run_with_timeout(1, ["sh", "-c", "sleep 5"])
    assert completed.returncode == 124
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert (
        capsys.readouterr().err
        == "mutation-gate: timeout unavailable (install coreutils for gtimeout); "
        "run is unbounded\n"
    )


# ---------------------------------------------------------------------------
# detect_result — the exit_code == -1 sentinel (unknown → classify by output)
# ---------------------------------------------------------------------------


def test_detect_result_sentinel_minus_one_falls_through_to_output_pass():
    body = json.dumps({"tool_response": {"exit_code": -1, "output": "5 passing"}})
    assert lib.detect_result(body) == "pass"


def test_detect_result_sentinel_minus_one_no_pattern_is_fail():
    body = json.dumps({"tool_response": {"exit_code": -1, "output": "nothing here"}})
    assert lib.detect_result(body) == "fail"


def test_detect_result_real_nonzero_exit_beats_pass_output():
    # A genuine nonzero exit is authoritative — a pass word in stdout must not flip it.
    body = json.dumps({"tool_response": {"exit_code": 1, "output": "5 passing"}})
    assert lib.detect_result(body) == "fail"


# ---------------------------------------------------------------------------
# _state_dir / state_file_path — TMPDIR resolution + digest shape
# ---------------------------------------------------------------------------


def test_state_dir_uses_tmpdir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert lib._state_dir() == tmp_path / "mutation-gate"


def test_state_dir_defaults_to_slash_tmp_when_no_tmpdir(monkeypatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    assert lib._state_dir() == Path("/tmp") / "mutation-gate"


def test_state_file_path_has_twelve_char_session_digest(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    name = lib.state_file_path().name
    assert name.startswith("session-")
    assert len(name) == len("session-") + 12


# ---------------------------------------------------------------------------
# write_state / read_state — mkdir idempotency, malformed input, purge, corrupt
# ---------------------------------------------------------------------------


def test_write_state_tolerates_repeated_calls(hermetic_state):
    lib.write_state("pass", _event_json(exit_code=0, output="a"))
    lib.write_state("fail", _event_json(exit_code=1, output="b"))
    assert json.loads(lib.read_state())["result"] == "fail"


def test_write_state_handles_malformed_event_json(hermetic_state):
    lib.write_state("pass", "not valid json{")
    assert json.loads(lib.read_state())["runner_stdout"] == ""


def test_write_state_purges_stale_session_files(hermetic_state):
    state_dir = lib._state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    old = state_dir / "session-oldoldoldold"
    old.write_text("{}")
    long_ago = time.time() - 20000
    os.utime(old, (long_ago, long_ago))
    lib.write_state("pass", _event_json(exit_code=0, output="x"))
    assert not old.exists()


def test_read_state_returns_empty_on_corrupt_file(hermetic_state):
    path = lib.state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{corrupt json")
    assert lib.read_state() == ""


def test_write_state_creates_nested_state_dir(monkeypatch, tmp_path):
    # TMPDIR points at a not-yet-existing nested path — the state dir must be
    # created with all missing parents (mkdir(parents=True)).
    nested = tmp_path / "deep" / "tmp"
    monkeypatch.setenv("TMPDIR", str(nested))
    monkeypatch.chdir(tmp_path)
    lib.write_state("pass", _event_json(exit_code=0, output="x"))
    assert (nested / "mutation-gate").is_dir()


def test_write_state_truncates_at_boundary_plus_one(hermetic_state):
    # One byte over the 65536 cap must still be truncated to exactly 65536.
    out = "y" * 65537
    lib.write_state("pass", _event_json(exit_code=0, output=out))
    assert len(json.loads(lib.read_state())["runner_stdout"]) == 65536


# ---------------------------------------------------------------------------
# is_test_command / detect_adapter — token-boundary + head-membership edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    ["mvnw test", "gradlew test", "npx vitest", "go test", "python pytest"],
)
def test_is_test_command_extra_true_cases(cmd):
    assert lib.is_test_command(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    ["npx", "npm", "mvn", "gradle", "dotnet", "go", "cargo", "node pytest"],
)
def test_is_test_command_bare_or_foreign_head_is_false(cmd):
    assert lib.is_test_command(cmd) is False


@pytest.mark.parametrize(
    "cmd,expected",
    [
        ("", "none"),
        ("npm", "none"),
        ("npx", "none"),
        ("mvnw test", "pitest"),
        ("gradlew test", "pitest"),
        ("npx vitest", "stryker"),
        ("python pytest", "mutmut"),
        ("python3 script.py", "none"),
        ("python", "none"),
    ],
)
def test_detect_adapter_extra_cases(cmd, expected):
    assert lib.detect_adapter(cmd) == expected


# ---------------------------------------------------------------------------
# first_changed_file — exact git argv + subprocess kwargs
# ---------------------------------------------------------------------------


def test_first_changed_file_uses_exact_git_argv_and_kwargs(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, check):
        calls.append((cmd, capture_output, text, check))
        return lib.subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    lib.first_changed_file(lambda _line: False)

    assert calls[0][0] == ["git", "diff", "--name-only", "HEAD"]
    assert calls[1][0] == ["git", "diff", "--cached", "--name-only"]
    # kwargs: capture_output=True, text=True, check=False.
    assert calls[0][1] is True
    assert calls[0][2] is True
    assert calls[0][3] is False


# ---------------------------------------------------------------------------
# parse_stryker_kills — exact advisory text + zero-kill dict shape
# ---------------------------------------------------------------------------


def test_parse_stryker_kills_missing_report_advisory_exact_text(tmp_path):
    out = tmp_path / "zk.json"
    missing = tmp_path / "nope.json"
    advisory = lib.parse_stryker_kills(missing, out)
    ctx = json.loads(advisory)["hookSpecificOutput"]["additionalContext"]
    assert ctx == (
        f"MUTATION GATE ADVISORY: Stryker report not found at {missing}. "
        "Run completed without mutation gate."
    )


def test_parse_stryker_kills_zero_kill_dict_has_null_file_and_line(tmp_path):
    out = tmp_path / "zk.json"
    lib.parse_stryker_kills(_STRYKER_FIXTURES / "mutation-zero-kill.json", out)
    data = json.loads(out.read_text())
    assert data[0]["file"] is None
    assert data[0]["line"] is None


# ---------------------------------------------------------------------------
# format_blocking_reason — exact line-by-line output (kills string mutants)
# ---------------------------------------------------------------------------


def test_format_blocking_reason_emits_exact_header_and_body_lines(tmp_path):
    payload = [{"name": "testA", "file": "src/calc.ts", "line": 10, "covered": 3}]
    zk = tmp_path / "zk.json"
    zk.write_text(json.dumps(payload))
    lines = lib.format_blocking_reason(zk, "npm test").split("\n")

    assert lines[0] == (
        "MUTATION GATE BLOCKED: zero-kill tests detected after RED-GREEN transition"
    )
    assert lines[1] == ""
    assert lines[2] == (
        "These tests covered mutants but killed none — they provide no regression safety."
    )
    assert lines[3] == (
        "A useful assertion changes the expected value when the implementation changes"
    )
    assert lines[4] == "(e.g., assert result === 5, not assert result !== undefined)."
    assert lines[5] == (
        "Rewrite each to assert the precise return value or side effect, or remove it:"
    )
    assert lines[6] == ""
    assert "  - testA  (src/calc.ts:10)" in lines
    assert "    Covered 3 mutants, killed 0" in lines
    # Each entry is followed by a blank separator line before the footer.
    assert lines[-2] == ""
    assert lines[-1] == "Fix these tests before continuing."


def test_format_blocking_reason_uses_unknown_and_zero_defaults(tmp_path):
    # An entry missing "name" and "covered" exercises the dict.get defaults.
    payload = [{"file": None, "line": None}]
    zk = tmp_path / "zk.json"
    zk.write_text(json.dumps(payload))
    lines = lib.format_blocking_reason(zk, "npm test").split("\n")
    assert "  - <unknown>  (<unknown>:<unknown>)" in lines
    assert "    Covered 0 mutants, killed 0" in lines
