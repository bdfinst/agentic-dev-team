"""Shared library for mutation-gate hook and adapters — Python port of lib.sh.

Adapter contract (mirrors the bash lib.sh header):

Inputs (env vars set by mutation-gate orchestrator):
  ADAPTER_COMMAND       — the original test command (used for pitest class extraction)
  ADAPTER_SOURCE_FILE   — path to the source file under test (JS/TS adapters)
  ADAPTER_TIMEOUT       — seconds (from MUTATION_GATE_TIMEOUT, default 60)
  ADAPTER_RUNNER_STDOUT — captured test runner stdout (for pitest test-list derivation)

Output: adapter writes normalized zero-kill list to $TMPDIR/mutation-gate/zero-kills.json
  Format: [{"name":"TestName","file":"path.ts","line":12,"covered":4}]
  "line" is null when unknown.

Exit codes: 0 = success or advisory (orchestrator reads zero-kills.json), 1 = internal error.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# _timeout — portable wrapper: `timeout` > `gtimeout` > unbounded fallback
# ---------------------------------------------------------------------------


def run_with_timeout(
    seconds: int,
    argv: Sequence[str],
    **kwargs: Any,
) -> "subprocess.CompletedProcess[bytes]":
    """Run `argv` with the given `seconds` wall-clock cap, mirroring bash `_timeout`.

    Prefers `timeout`/`gtimeout` on PATH (so the runner keeps its bash-native
    kill semantics on hosts that have coreutils); falls back to
    `subprocess.run(..., timeout=...)` when neither is available. On timeout,
    return code is 124 to match `timeout(1)`'s convention.

    All extra kwargs pass through to `subprocess.run`. Callers pass `check=False`
    when they want to inspect the exit code themselves.
    """
    kwargs.setdefault("check", False)
    timeout_bin = shutil.which("timeout") or shutil.which("gtimeout")
    if timeout_bin is not None:
        return subprocess.run([timeout_bin, str(seconds), *argv], **kwargs)
    # No coreutils timeout available — emit the same advisory as bash lib
    # to stderr so the JSON stdout channel stays clean.
    sys.stderr.write(
        "mutation-gate: timeout unavailable (install coreutils for gtimeout); "
        "run is unbounded\n"
    )
    try:
        return subprocess.run(list(argv), timeout=seconds, **kwargs)
    except subprocess.TimeoutExpired as exc:
        # Synthesize a CompletedProcess with the timeout-native exit code so
        # callers keep their `exit == 124` branch.
        return subprocess.CompletedProcess(
            args=list(argv),
            returncode=124,
            stdout=exc.stdout or b"",
            stderr=exc.stderr or b"",
        )


# ---------------------------------------------------------------------------
# JSON output helpers
#
# The bash lib pipes through `jq -n` to build objects; here we compose with
# `json.dumps` and preserve the same key order + no trailing newline so the
# hook's JSON decision channel stays byte-parity with the bash implementation.
# ---------------------------------------------------------------------------


def emit_block(reason: str) -> str:
    """Return `{"decision":"block","reason":"..."}` as compact JSON (no trailing \\n)."""
    return json.dumps({"decision": "block", "reason": reason})


def emit_advisory(message: str) -> str:
    """Return the PostToolUse additionalContext envelope for an advisory message."""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": message,
            }
        }
    )


# ---------------------------------------------------------------------------
# State file management — mirrors bash lib
#
# Location: $TMPDIR/mutation-gate/session-<12-char sha256 of cwd>
# TTL: 4 hours (14400 seconds)
# ---------------------------------------------------------------------------


_STATE_TTL_SECONDS = 14400


def _state_dir() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "mutation-gate"


def state_file_path(cwd: Optional[Path] = None) -> Path:
    """Return the per-project state file path (`session-<hash>`)."""
    base = str(cwd if cwd is not None else Path.cwd())
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
    return _state_dir() / f"session-{digest}"


def _purge_stale_states(state_dir: Path) -> None:
    """Delete session-* files older than TTL. Best-effort; errors ignored."""
    if not state_dir.is_dir():
        return
    now = time.time()
    for path in state_dir.glob("session-*"):
        try:
            if now - path.stat().st_mtime > _STATE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def write_state(result: str, event_json: str, cwd: Optional[Path] = None) -> None:
    """Write the state file from a PostToolUse event body.

    `result` is "pass" or "fail"; `event_json` is the raw stdin JSON string —
    we extract `tool_response.output` and truncate it to 64 KiB, matching the
    bash `head -c 65536` behaviour.
    """
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _purge_stale_states(state_dir)
    try:
        event = json.loads(event_json) if event_json else {}
    except (TypeError, ValueError):
        event = {}
    tool_response = event.get("tool_response") or {}
    runner_stdout = tool_response.get("output") or ""
    if len(runner_stdout) > 65536:
        runner_stdout = runner_stdout[:65536]
    payload = {
        "result": result,
        "timestamp": int(time.time()),
        "runner_stdout": runner_stdout,
    }
    target = state_file_path(cwd)
    target.write_text(json.dumps(payload))


def read_state(cwd: Optional[Path] = None) -> str:
    """Return the state JSON as a string, or `""` if absent / stale.

    Stale files (> TTL) are deleted lazily on read so subsequent calls don't
    keep re-reading them.
    """
    path = state_file_path(cwd)
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return ""
    ts = data.get("timestamp") or 0
    if int(time.time()) - int(ts) > _STATE_TTL_SECONDS:
        try:
            path.unlink()
        except OSError:
            pass
        return ""
    return path.read_text()


# ---------------------------------------------------------------------------
# Result detection
# ---------------------------------------------------------------------------


_PASS_PATTERNS = re.compile(
    r"passing|tests run.*failures: 0|all tests passed|✓|ok [0-9]",
    re.IGNORECASE,
)
_FAIL_PATTERNS = re.compile(
    r"failing|failures: [1-9]|error:|FAILED",
    re.IGNORECASE,
)


def detect_result(event_json: str) -> str:
    """Return "pass" or "fail" for a PostToolUse event.

    Primary signal: `tool_response.exit_code`. Secondary: stdout patterns —
    used for runners that always exit 0. Default: "fail" when uncertain (the
    bash lib does the same).
    """
    try:
        event = json.loads(event_json) if event_json else {}
    except (TypeError, ValueError):
        event = {}
    tool_response = event.get("tool_response") or {}
    exit_code = tool_response.get("exit_code")
    if exit_code == 0:
        return "pass"
    if exit_code is not None and exit_code != -1:
        return "fail"
    output = tool_response.get("output") or ""
    if _PASS_PATTERNS.search(output):
        return "pass"
    if _FAIL_PATTERNS.search(output):
        return "fail"
    return "fail"


def is_red_to_green(prev_result: str, cur_result: str) -> bool:
    """Return True if `prev_result` = fail and `cur_result` = pass."""
    return prev_result == "fail" and cur_result == "pass"


# ---------------------------------------------------------------------------
# Test command detection
# ---------------------------------------------------------------------------


def _tokens(command: str) -> List[str]:
    return command.strip().split()


def is_test_command(command: str) -> bool:
    """Return True when `command` looks like a supported test runner invocation."""
    tokens = _tokens(command)
    if not tokens:
        return False
    head = tokens[0]
    if head == "npm":
        if len(tokens) >= 2 and tokens[1] == "test":
            return True
        if len(tokens) >= 3 and tokens[1] == "run" and tokens[2] == "test":
            return True
        return False
    if head == "npx" and len(tokens) >= 2 and tokens[1] in {"vitest", "jest"}:
        return True
    if (
        head in {"mvn", "./mvnw", "mvnw"}
        and len(tokens) >= 2
        and tokens[1]
        in {
            "test",
            "verify",
        }
    ):
        return True
    if (
        head in {"gradle", "./gradlew", "gradlew"}
        and len(tokens) >= 2
        and tokens[1] == "test"
    ):
        return True
    if head == "dotnet" and len(tokens) >= 2 and tokens[1] == "test":
        return True
    if head == "pytest":
        return True
    if head in {"python", "python3"} and any("pytest" in t for t in tokens[1:]):
        return True
    if head == "go" and len(tokens) >= 2 and tokens[1] == "test":
        return True
    if head == "cargo" and len(tokens) >= 2 and tokens[1] == "test":
        return True
    return False


# ---------------------------------------------------------------------------
# Adapter dispatch
# ---------------------------------------------------------------------------


def detect_adapter(command: str) -> str:
    """Return one of stryker | pitest | stryker-net | mutmut | none."""
    tokens = _tokens(command)
    if not tokens:
        return "none"
    head = tokens[0]
    if head == "npm" and (
        (len(tokens) >= 2 and tokens[1] == "test")
        or (len(tokens) >= 3 and tokens[1] == "run" and tokens[2] == "test")
    ):
        return "stryker"
    if head == "npx" and len(tokens) >= 2 and tokens[1] in {"vitest", "jest"}:
        return "stryker"
    if (
        head in {"mvn", "./mvnw", "mvnw"}
        and len(tokens) >= 2
        and tokens[1]
        in {
            "test",
            "verify",
        }
    ):
        return "pitest"
    if (
        head in {"gradle", "./gradlew", "gradlew"}
        and len(tokens) >= 2
        and tokens[1] == "test"
    ):
        return "pitest"
    if head == "dotnet" and len(tokens) >= 2 and tokens[1] == "test":
        return "stryker-net"
    if head == "pytest":
        return "mutmut"
    if head in {"python", "python3"}:
        # python -m pytest, python3 -m pytest, python somefile-pytest, python -m unittest
        for t in tokens[1:]:
            if "pytest" in t or "unittest" in t:
                return "mutmut"
        return "none"
    return "none"


# ---------------------------------------------------------------------------
# First changed source file — shared by pitest / stryker-net / mutmut adapters
#
# Each adapter needs "the first non-test source file touched by this change"
# to scope its mutation run (target class, --mutate pattern, --paths-to-mutate).
# The traversal (git diff --name-only HEAD, falling back to --cached) is
# identical across adapters; only the extension set and test-name exclusion
# differ, so those are supplied as a single predicate.
# ---------------------------------------------------------------------------


def first_changed_file(is_source_predicate: Callable[[str], bool]) -> str:
    """Return the first changed file for which `is_source_predicate` is True.

    Checks `git diff --name-only HEAD` first, then falls back to
    `git diff --cached --name-only` (mirrors the bash adapters' behaviour of
    preferring unstaged/working-tree changes over already-staged ones).
    Returns "" when git is unavailable or no line satisfies the predicate.
    """
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--cached", "--name-only"],
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except (FileNotFoundError, OSError):
            return ""
        for line in proc.stdout.splitlines():
            if is_source_predicate(line):
                return line
    return ""


# ---------------------------------------------------------------------------
# Zero-kill parsing (Stryker JSON schema, shared by stryker + stryker-net)
# ---------------------------------------------------------------------------


def parse_stryker_kills(report_file: Path, output_file: Path) -> Optional[str]:
    """Parse Stryker JSON, write zero-kills to `output_file`.

    Returns None on success; returns the advisory JSON string when the report
    is missing (mirrors bash: bash emits the advisory to stdout, callers
    forward it). Caller writes `[]` to `output_file` in that path already so
    the return value is only consumed for the advisory.
    """
    report_file = Path(report_file)
    output_file = Path(output_file)
    if not report_file.is_file():
        advisory = emit_advisory(
            f"MUTATION GATE ADVISORY: Stryker report not found at {report_file}. "
            "Run completed without mutation gate."
        )
        try:
            output_file.write_text("[]")
        except OSError:
            pass
        return advisory

    data = json.loads(report_file.read_text())
    mutants = data.get("mutants", [])

    killing_set = set()
    coverage: Dict[str, int] = {}
    for mutant in mutants:
        for t in mutant.get("killedBy", []):
            killing_set.add(t)
        for t in mutant.get("coveredBy", []):
            coverage[t] = coverage.get(t, 0) + 1

    zero_kills: List[Dict[str, Any]] = []
    for test in sorted(set(coverage.keys()) - killing_set):
        zero_kills.append(
            {
                "name": test,
                "file": None,
                "line": None,
                "covered": coverage[test],
            }
        )

    output_file.write_text(json.dumps(zero_kills))
    return None


# ---------------------------------------------------------------------------
# Blocking-reason formatter — same output as the bash inline Python heredoc.
# ---------------------------------------------------------------------------


def format_blocking_reason(zero_kills_file: Path, command: str) -> str:  # noqa: ARG001
    """Return the multi-line human-readable reason string for a blocked gate.

    `command` is unused (kept for signature parity with bash) — the message
    catalogs the zero-kill tests read from `zero_kills_file`.
    """
    with open(zero_kills_file) as f:
        zero_kills = json.load(f)

    lines = [
        "MUTATION GATE BLOCKED: zero-kill tests detected after RED-GREEN transition",
        "",
        "These tests covered mutants but killed none — they provide no regression safety.",
        "A useful assertion changes the expected value when the implementation changes",
        "(e.g., assert result === 5, not assert result !== undefined).",
        "Rewrite each to assert the precise return value or side effect, or remove it:",
        "",
    ]
    for zk in zero_kills:
        name = zk.get("name", "<unknown>")
        file_ = zk.get("file") or "<unknown>"
        line = zk.get("line")
        loc = f"({file_}:{line})" if line else f"({file_}:<unknown>)"
        covered = zk.get("covered", 0)
        lines.append(f"  - {name}  {loc}")
        lines.append(f"    Covered {covered} mutants, killed 0")
        lines.append("")

    lines.append("Fix these tests before continuing.")
    return "\n".join(lines)
