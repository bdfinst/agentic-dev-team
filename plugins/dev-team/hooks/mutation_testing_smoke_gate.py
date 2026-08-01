#!/usr/bin/env python3
"""Mutation-testing smoke gate — PreToolUse hook (#565; python port per #574 / #572).

Byte-compatible port of the Claude Code PreToolUse hook that enforces the
SKILL.md § Step 1c smoke gate. Blocks whole-scope Stryker.NET invocations
until a single-file smoke probe has landed a mutation-report.json under
StrykerOutput/smoke/reports/ with at least one Killed mutant.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: exit 2 + message on stdout to BLOCK
            exit 0 + no stdout for SILENT-PASS
            exit 0 + ADVISORY-prefixed stdout for missing-dep / malformed / drift
    Env   : MUTATION_SMOKE_GATE_SKIP=1 → silent bypass + audit-log line

Stdlib-only. See docs/python-hook-contract.md.

Refs: #565 (the .sh predecessor), #554, #557 (the failure modes it guards).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
import artifact_paths  # type: ignore[import-not-found]

try:
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        return None

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


# ---------------------------------------------------------------------------
# Trigger detection
# ---------------------------------------------------------------------------


_STRYKER_TRIGGER = re.compile(
    r"(?:^|[^a-zA-Z0-9])dotnet[ \t]+stryker(?:\b|$)|csharp-stryker-net-wrapper\.sh"
)


def is_stryker_command(cmd: str) -> bool:
    """True when `cmd` invokes dotnet stryker OR the wrapper script."""
    if not cmd:
        return False
    return bool(_STRYKER_TRIGGER.search(cmd))


def extract_mutate_value(cmd: str) -> str:
    """Return the --mutate value (handles --mutate=X, --mutate X, -m X).

    Respects shell quoting via shlex so `--mutate 'src/Foo.cs'` and
    `--mutate "src/Foo.cs"` both yield the unquoted path. Malformed shell
    input yields "" (silent, matching the .sh's behavior).
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return ""
    for i, tok in enumerate(tokens):
        if tok.startswith("--mutate="):
            return tok.split("=", 1)[1]
        if tok in ("--mutate", "-m"):
            if i + 1 < len(tokens):
                return tokens[i + 1]
            return ""
    return ""


def is_single_file_mutate(value: str) -> bool:
    """A --mutate value is single-file only when it has no glob metacharacters
    (*, ?, [) AND no semicolon (Stryker.NET's multi-file separator)."""
    if not value:
        return False
    return not any(c in value for c in ("*", "?", "[", ";"))


# ---------------------------------------------------------------------------
# Audit-log helpers
# ---------------------------------------------------------------------------


def sha256_first_16(text: str) -> str:
    """First 16 hex chars of sha256(text). Matches the .sh's cross-platform
    shasum/sha256sum fallback chain output."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def iso_utc_timestamp() -> str:
    """ISO-8601 UTC timestamp with 'Z' suffix. Matches the .sh helper."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_bypass_audit(raw_command: str, payload_cwd: str) -> None:
    """Append one JSONL line to <payload_cwd>/.claude/metrics/gate-bypass.jsonl.

    Writes timestamp + hook name + command_hash (sha256 first 16) + cwd.
    The raw command is NEVER written — only its hash — matching the .sh's
    privacy boundary. Filesystem errors write to stderr and return
    silently so the bypass still succeeds.
    """
    audit_file = artifact_paths.resolve_file(
        "metrics", "gate-bypass.jsonl", payload_cwd
    )
    audit_dir = audit_file.parent
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        print(
            f"mutation-testing-smoke-gate: cannot create {audit_dir} "
            "(bypass still succeeds)",
            file=sys.stderr,
        )
        return
    record = {
        "timestamp": iso_utc_timestamp(),
        "hook": "mutation-testing-smoke-gate",
        "command_hash": sha256_first_16(raw_command),
        "cwd": payload_cwd,
    }
    try:
        with audit_file.open("a", encoding="utf-8") as fh:
            # Match jq -c compact output: no spaces after ',' or ':'.
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        print(
            f"mutation-testing-smoke-gate: cannot write to {audit_file} "
            "(bypass still succeeds)",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Block message
# ---------------------------------------------------------------------------


_BLOCK_TEMPLATE = """[BLOCK] mutation-testing-smoke-gate: whole-scope Stryker.NET run detected

{diagnostic}

The Step 1c smoke gate (see SKILL.md § Step 1c) requires a single-file
mutation probe with Killed > 0 before authorizing a full run. This
prevents the silent 0.00 % failure mode (see #554, #557).

To run the smoke probe:

  dotnet stryker --config-file stryker-config.json \\
    --mutate 'path/to/one/covered/file.cs' \\
    -O StrykerOutput/smoke

Then re-run this command. To bypass this gate for a legitimate exception,
set MUTATION_SMOKE_GATE_SKIP=1 in the environment (audit-logged)."""


def print_block_message(diagnostic: str) -> None:
    """Write the shared block-message body with the caller's diagnostic."""
    print(_BLOCK_TEMPLATE.format(diagnostic=diagnostic))


# ---------------------------------------------------------------------------
# Report parsing
# ---------------------------------------------------------------------------


def count_mutants_by_status(report: dict, status: str) -> int:
    """Count entries in report['mutants'] with the given status field."""
    mutants = report.get("mutants") or []
    return sum(1 for m in mutants if isinstance(m, dict) and m.get("status") == status)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main() -> int:
    # -------------------------------------------------------------------
    # Dependency guards — a missing dep must NOT become a de facto gate.
    # -------------------------------------------------------------------
    if shutil.which("jq") is None:
        # Preserve parity with the .sh, which uses jq for JSON parsing.
        # The Python port does not itself use jq, but flags the missing
        # dep to keep the failure mode identical across ports.
        print(
            "ADVISORY: mutation-testing-smoke-gate: jq is required but not installed; gate not enforced"
        )
        return 0
    # python3 is always present by construction in a .py hook; the .sh's
    # python3 dep check is a no-op here.

    # -------------------------------------------------------------------
    # Parse PreToolUse payload
    # -------------------------------------------------------------------
    payload = read_stdin_json()
    if payload is None:
        # Empty or malformed stdin — nothing to check, silent-pass.
        return 0

    command = str(payload.get("tool_input", {}).get("command", "") or "")
    if not command:
        return 0

    # cwd from payload, fall back to $PWD (matches .sh's `${PAYLOAD_CWD:=$PWD}`).
    # Prefer the shell-provided $PWD over os.getcwd() so macOS's /var → /private/var
    # symlink resolution does not diverge from the .sh.
    payload_cwd = str(payload.get("cwd") or os.environ.get("PWD") or os.getcwd())

    # -------------------------------------------------------------------
    # Trigger detection
    # -------------------------------------------------------------------
    if not is_stryker_command(command):
        return 0

    mutate_value = extract_mutate_value(command)
    if is_single_file_mutate(mutate_value):
        # This IS the smoke probe; do not block it.
        return 0

    # -------------------------------------------------------------------
    # Escape hatch — must run BEFORE report check so bypass works even
    # without a report. Matches .sh ordering.
    # -------------------------------------------------------------------
    if os.environ.get("MUTATION_SMOKE_GATE_SKIP", "0") == "1":
        log_bypass_audit(command, payload_cwd)
        return 0

    # -------------------------------------------------------------------
    # Whole-scope run detected — check the smoke report.
    # -------------------------------------------------------------------
    report_path = (
        Path(payload_cwd)
        / "StrykerOutput"
        / "smoke"
        / "reports"
        / "mutation-report.json"
    )

    session_id = payload.get("session_id")

    if not report_path.is_file():
        print_block_message(f"no smoke report at {report_path}")
        emit_boundary_event(
            payload_cwd, "mutation_testing_smoke_gate", "Bash", "block",
            "mutation-smoke-report-missing", session_id,
        )
        return 2

    try:
        report_text = report_path.read_text(encoding="utf-8")
    except OSError:
        print_block_message(f"no smoke report at {report_path}")
        emit_boundary_event(
            payload_cwd, "mutation_testing_smoke_gate", "Bash", "block",
            "mutation-smoke-report-missing", session_id,
        )
        return 2

    try:
        report = json.loads(report_text)
    except json.JSONDecodeError:
        # Malformed JSON — advisory (not block, not silent-pass). Matches .sh.
        print(
            f"ADVISORY: mutation-testing-smoke-gate: report at {report_path} is not valid JSON — cannot enforce gate; command not blocked"
        )
        return 0

    # Schema drift — valid JSON without mutants[]. Advisory. ORDERING NOTE
    # (from .sh): schema-drift advisory MUST run before counting logic;
    # otherwise a schema-drift report incorrectly reports "no scored mutants".
    if not isinstance(report, dict) or "mutants" not in report:
        print(
            f"ADVISORY: mutation-testing-smoke-gate: report at {report_path} lacks the mutants[] key — not the mutation-testing-elements shape; cannot enforce gate"
        )
        return 0

    killed = count_mutants_by_status(report, "Killed")
    survived = count_mutants_by_status(report, "Survived")

    # At least one Killed → gate passes silently.
    if killed > 0:
        return 0

    # Killed==0 && Survived>0 → mutation-switch not observing mutations.
    if survived > 0:
        print_block_message(
            f"killed=0 survived={survived} — mutation-switch not observing mutations at runtime "
            "(see #554, #557 and SKILL.md Step 1c diagnostic checklist)"
        )
        emit_boundary_event(
            payload_cwd, "mutation_testing_smoke_gate", "Bash", "block",
            "mutation-smoke-switch-not-observed", session_id,
        )
        return 2

    # Killed==0 && Survived==0 → empty mutants[] or only NoCoverage/CompileError.
    print_block_message(
        "no scored mutants in smoke report — pick a different probe file with real test coverage"
    )
    emit_boundary_event(
        payload_cwd, "mutation_testing_smoke_gate", "Bash", "block",
        "mutation-smoke-no-scored-mutants", session_id,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
