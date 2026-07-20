#!/usr/bin/env python3
"""session_learning_trigger.py — SessionEnd hook (Python port of session-learning-trigger.sh).

Counts sessions and dispatches background session-analysis at threshold.

CONSENT : off by default. Set `DEV_TEAM_AUTO_REVIEW=on` to enable.
THRESHOLD: `DEV_TEAM_AUTO_REVIEW_THRESHOLD` (default 5) sessions before dispatch.
STATE    : counter persisted in `<cwd>/metrics/learning-loop-state.json`.

Posture: fail-open. Every I/O error exits 0 without crashing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def _load_counter(state_file: Path) -> int:
    """Return the persisted counter, recovering to 0 on any error."""
    if not state_file.is_file():
        return 0
    try:
        data = json.loads(state_file.read_text())
    except (OSError, ValueError):
        return 0
    counter = data.get("counter")
    if isinstance(counter, int) and counter >= 0:
        return counter
    if isinstance(counter, str) and counter.isdigit():
        return int(counter)
    return 0


def _write_state(state_file: Path, counter: int) -> None:
    """Atomically write `{"counter": N}` to `state_file`. Fail-open on any error."""
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".learning-loop-state-",
            suffix=".json",
            dir=str(state_file.parent),
        )
    except OSError:
        return
    try:
        with os.fdopen(fd, "w") as handle:
            # `jq -nc` in bash writes with a trailing newline — match it so the
            # parity harness's side-effect tree hash lines up.
            handle.write(json.dumps({"counter": counter}, separators=(",", ":")) + "\n")
        os.replace(tmp_path, state_file)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _dispatch_background_analysis(
    cwd: Path, session_id: Optional[str], hook_dir: Path
) -> None:
    """Fire-and-forget background analysis run. Silent on any failure."""
    session_extract = (
        hook_dir / ".." / ".." / "scripts" / "session_extract.py"
    ).resolve()
    pending = cwd / "metrics" / "pending-review.jsonl"

    prompt = (
        "Run the session-analysis agent and output each finding as a JSONL "
        "entry to stdout with fields: queued_at (ISO-8601 UTC now), source "
        "(session-learning-trigger), session_id, findings (array of objects "
        "with lever, evidence, target_artifact, proposed_change, route)"
    )

    session_id_args = []
    if session_id:
        # --session-id shares the parent's prompt-cache prefix (~26% cost cut)
        session_id_args = ["--session-id", session_id]

    metrics_dir = cwd / "metrics"
    try:
        metrics_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    # Compose a shell script that runs asynchronously — same fire-and-forget
    # semantics as bash's `( ... ) &`.
    shell_body = (
        f"python3 {shell_quote(str(session_extract))} --since last "
        ">/dev/null 2>&1 || true; "
        f"tmp_out=$(mktemp {shell_quote(str(metrics_dir / '.pending-XXXXXX.jsonl'))} "
        "2>/dev/null) || exit 0; "
        f"if claude {' '.join(shell_quote(a) for a in session_id_args)} "
        f"--dangerously-skip-permissions --print {shell_quote(prompt)} "
        '>"$tmp_out" 2>/dev/null; then '
        f'cat "$tmp_out" >> {shell_quote(str(pending))} 2>/dev/null || true; fi; '
        'rm -f "$tmp_out"'
    )

    try:
        subprocess.Popen(  # noqa: S603 — intentional detached child
            ["sh", "-c", shell_body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, OSError):
        pass


def shell_quote(value: str) -> str:
    """Portable-ish single-quote quoting for POSIX sh."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> int:
    if os.environ.get("DEV_TEAM_AUTO_REVIEW", "") != "on":
        return 0

    # bash requires jq; Python does not, but keep parity on the "no jq" exit
    # for hosts that intentionally strip it (fail-open discipline).
    if shutil.which("jq") is None:
        return 0

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return 0

    cwd_str = payload.get("cwd") if isinstance(payload, dict) else None
    cwd = Path(cwd_str) if isinstance(cwd_str, str) and cwd_str else Path.cwd()
    if not cwd.is_dir():
        cwd = Path.cwd()

    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(session_id, str) or not session_id:
        session_id = None

    threshold_env = os.environ.get("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "5")
    try:
        threshold = int(threshold_env)
    except ValueError:
        threshold = 5

    state_file = cwd / "metrics" / "learning-loop-state.json"
    hook_dir = Path(__file__).resolve().parent

    counter = _load_counter(state_file) + 1

    if counter >= threshold:
        _write_state(state_file, 0)
        _dispatch_background_analysis(cwd, session_id, hook_dir)
    else:
        _write_state(state_file, counter)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
