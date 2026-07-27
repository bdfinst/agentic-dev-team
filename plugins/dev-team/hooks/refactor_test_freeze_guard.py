#!/usr/bin/env python3
"""refactor_test_freeze_guard.py — PreToolUse hook (Write|Edit), issue #813.

Enforces the tests-frozen-during-refactor invariant mechanically: while
`/build` has recorded that the current step is in its REFACTOR phase
(`.claude/memory/build-phase.json`), any Write/Edit targeting a test file is denied
(exit 2, `[BLOCK]` per docs/python-hook-contract.md). A refactor step must
never change a test — the invariant held at zero violations across the
experiment campaigns (Rec 4, docs/experiments/RECOMMENDATIONS.md).

Fails OPEN on any internal error, with one audit line in
`.claude/metrics/refactor-freeze.jsonl` — a broken guard must never block
work.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from boundary_events import emit_boundary_event as _emit_boundary_event
from stdin_json import read_stdin_json
from test_file_classify import is_test_file, read_build_phase


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass

def _project_dir() -> Path:
    """Resolve the project root via git, not the possibly-unset/stale
    CLAUDE_PROJECT_DIR env var."""
    return artifact_paths.project_root()


def audit(
    project_dir: Path,
    hook: str,
    event: str,
    file: str | None = None,
    step: str | None = None,
    reason: str | None = None,
) -> None:
    """Append one JSONL audit line under .claude/metrics/refactor-freeze.jsonl.

    Best-effort — a failure to resolve the path, create the directory, or
    write the line is fail-open: log a diagnostic and never crash the guard.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hook": hook,
        "event": event,
        "file": file,
        "step": step,
        "reason": reason,
    }
    try:
        path = artifact_paths.resolve_file("metrics", "refactor-freeze.jsonl", project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as exc:
        sys.stderr.write(f"[refactor_test_freeze_guard] failed to write audit line: {exc}\n")


def _extract_file_path(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return ""
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def evaluate(
    file_path: str, project_dir: Path, now: float | None = None
) -> tuple[int, list[str]]:
    """Return (exit_code, stdout_lines) for one Write/Edit decision."""
    if not file_path:
        return 0, []
    state, error = read_build_phase(project_dir, now=now)
    if error is not None:
        audit(project_dir, "freeze", "fail-open", file=file_path, reason=error)
        return 0, []
    if state is None or state.get("phase") != "refactor":
        return 0, []
    if not is_test_file(file_path):
        return 0, []
    step = state.get("step") if isinstance(state.get("step"), str) else None
    audit(project_dir, "freeze", "block", file=file_path, step=step)
    step_label = f" (step {step})" if step else ""
    return 2, [
        f"[BLOCK] Tests are frozen during REFACTOR{step_label}.",
        "A refactor step must never change a test — refactoring is",
        "behavior-preserving by definition (tests-frozen invariant, Rec 4,",
        "docs/experiments/RECOMMENDATIONS.md).",
        f"File: {file_path}",
        "Recovery: leave REFACTOR and return to the TEST phase, make the test",
        "change there, re-verify the full suite green (pasted evidence), then",
        "re-enter REFACTOR.",
    ]


def main() -> int:
    project_dir = _project_dir()
    try:
        payload = read_stdin_json()
        file_path = _extract_file_path(payload)
        exit_code, lines = evaluate(file_path, project_dir)
        if exit_code == 2:
            session_id = payload.get("session_id") if isinstance(payload, dict) else None
            emit_boundary_event(
                project_dir, "refactor_test_freeze_guard", "Write", "block",
                "refactor-test-freeze", session_id,
            )
    except Exception as exc:  # noqa: BLE001  # fail open — a broken guard never blocks work
        audit(project_dir, "freeze", "fail-open", reason=f"internal error: {exc}")
        return 0
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
