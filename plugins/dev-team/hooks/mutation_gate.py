#!/usr/bin/env python3
"""mutation_gate.py — PostToolUse hook (Python port of mutation-gate.sh).

After each RED-to-GREEN test transition, runs mutation testing scoped to
the affected test file and blocks tests that kill zero mutants.

Output protocol (PostToolUse):
  Blocking : `emit_block` JSON on stdout, exit 0.
  Advisory : `emit_advisory` JSON on stdout, exit 0.
  Silent   : no stdout, exit 0.

Delegates to `hooks.mutation_adapters` for detection, dispatch, and per-
adapter execution — the same Python library shipped in #572.D0.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


_HOOK_DIR = Path(__file__).resolve().parent
# Add the plugin hooks dir to sys.path so the mutation_adapters package resolves.
sys.path.insert(0, str(_HOOK_DIR))
sys.path.insert(0, str(_HOOK_DIR / "lib"))

from mutation_adapters import lib as adapter_lib  # noqa: E402
from mutation_adapters import mutmut, pitest, stryker, stryker_net  # noqa: E402
from boundary_events import emit_boundary_event as _emit_boundary_event  # noqa: E402


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


_JQ_MISSING_MESSAGE = (
    "MUTATION GATE ADVISORY: jq is required but not installed. Run "
    "/init-dev-team to install it, or: brew install jq (macOS) / apt install jq "
    "(Linux) / winget install jqlang.jq (Windows)."
)


def _emit_advisory_pretty(message: str) -> None:
    """Emit an advisory in bash `jq -n`'s pretty format (2-space indent + \\n).

    `mutation-gate.sh` prints its advisories with `jq -n` so downstream Claude
    Code output stays visually indented. This matches that shape byte-for-byte
    for the paths the mutation-gate hook itself dispatches; the adapters still
    print compact JSON (their internal `emit_advisory` returns compact),
    tracked for the next release cycle when the settings-toggle flips
    default to `.py`.
    """
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": message,
                }
            },
            indent=2,
        )
    )


def _emit_block_pretty(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, indent=2))


def main() -> int:
    # Hard dependency guards — mirror the bash order.
    if shutil.which("jq") is None:
        _emit_advisory_pretty(_JQ_MISSING_MESSAGE)
        return 0
    # python3 is by definition available here (we are python3), but if the
    # bash sibling migrates a caller through the settings-toggle env var, the
    # advisory would already have fired. Keep the branch for parity of the
    # shape, harmlessly no-op.

    if os.environ.get("MUTATION_GATE_SKIP") == "1":
        return 0

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    command = ""
    tool_input = payload.get("tool_input") or {}
    if isinstance(tool_input, dict):
        candidate = tool_input.get("command")
        if isinstance(candidate, str):
            command = candidate
    if not command:
        return 0

    if not adapter_lib.is_test_command(command):
        return 0

    event_json = raw
    current_result = adapter_lib.detect_result(event_json)

    prev_state = adapter_lib.read_state()
    prev_result = "none"
    if prev_state:
        try:
            prev_result = json.loads(prev_state).get("result") or "none"
        except (TypeError, ValueError):
            prev_result = "none"

    adapter_lib.write_state(current_result, event_json)

    if not adapter_lib.is_red_to_green(prev_result, current_result):
        return 0

    adapter = adapter_lib.detect_adapter(command)
    if adapter == "none":
        _emit_advisory_pretty(
            "MUTATION GATE ADVISORY: no mutation testing adapter for this "
            "language. Run /init-dev-team to install one (supports JS/TS via "
            "Stryker, Java via pitest, C# via Stryker.NET)."
        )
        return 0

    zero_kills_dir = Path(os.environ.get("TMPDIR", "/tmp")) / "mutation-gate"
    zero_kills_file = zero_kills_dir / "zero-kills.json"
    zero_kills_dir.mkdir(parents=True, exist_ok=True)

    os.environ["ADAPTER_TIMEOUT"] = os.environ.get("MUTATION_GATE_TIMEOUT", "60")
    os.environ["ADAPTER_COMMAND"] = command

    runner_stdout = ""
    if prev_state:
        try:
            runner_stdout = json.loads(prev_state).get("runner_stdout") or ""
        except (TypeError, ValueError):
            runner_stdout = ""
    os.environ["ADAPTER_RUNNER_STDOUT"] = runner_stdout

    if adapter == "stryker":
        if not stryker.stryker_detect():
            return 0
        # bash derives ADAPTER_SOURCE_FILE from the last word of the command.
        last_arg = command.rsplit(" ", 1)[-1] if command else ""
        source_file = stryker.derive_source_file(last_arg) if last_arg else ""
        os.environ["ADAPTER_SOURCE_FILE"] = source_file
        stryker.stryker_run(zero_kills_file)
    elif adapter == "pitest":
        if not pitest.pitest_detect():
            return 0
        pitest.pitest_run(zero_kills_file)
    elif adapter == "stryker-net":
        if not stryker_net.stryker_net_detect():
            return 0
        stryker_net.stryker_net_run(zero_kills_file)
    elif adapter == "mutmut":
        if not mutmut.mutmut_detect():
            return 0
        mutmut.mutmut_run(zero_kills_file)

    # Emit block if zero-kill tests found.
    if zero_kills_file.is_file():
        try:
            data = json.loads(zero_kills_file.read_text())
        except (OSError, ValueError):
            data = []
        if isinstance(data, list) and data:
            reason = adapter_lib.format_blocking_reason(zero_kills_file, command)
            _emit_block_pretty(reason)
            emit_boundary_event(
                payload.get("cwd") or ".", "mutation_gate", "Bash", "block",
                "mutation-gate-zero-kills", payload.get("session_id"),
            )

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
