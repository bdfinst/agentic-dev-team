#!/usr/bin/env python3
"""SessionStart hook: notify when the pending-review queue has entries.

Emits a one-line notification when .claude/metrics/pending-review.jsonl has
unreviewed entries. Split off (#1284/#1288) from the retired
session_model_banner.py, whose other two responsibilities (persisting the
session model to `.claude/session-model` and announcing the effort-band
routing table) belonged to the band-to-model resolver system ADR 0026
retired — the harness now resolves `model:`/`effort:` natively, with no
plugin-side banner to keep in sync.

Env seams (TEST-ONLY):
    PENDING_REVIEW_FILE  defaults to <cwd>/.claude/metrics/pending-review.jsonl

Contract (docs/python-hook-contract.md):
    Input : SessionStart JSON on stdin (hook_event_name, cwd, model, ...).
    Output: notification text on stdout. Exit 0 always.
    Posture: fail-open — a buggy notifier must never block a session.

Stdlib-only (json/os/pathlib/sys).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths


def _notify_pending_findings(cwd: str) -> str | None:
    """Count still-pending entries in the pending-review queue, rotating out
    disposed ones so the file stays bounded (#732).

    A finding gains exactly one disposition (`reviewed_at` on approval,
    `rejected_at` on rejection — see feedback-learning/SKILL.md); once either
    is present, its audit trail lives in .claude/metrics/config-changelog.jsonl
    (on approval) and the entry itself has no further use here. Rewriting the
    queue to drop disposed entries every SessionStart keeps it bounded to the
    outstanding backlog instead of growing without limit across the life of
    a project. Lines that fail to parse can't be classified either way, so
    they are left untouched — /session-review handles malformed-line
    reporting on its own.
    """
    queue_env = os.environ.get("PENDING_REVIEW_FILE")
    queue = (
        Path(queue_env)
        if queue_env
        else artifact_paths.resolve_file("metrics", "pending-review.jsonl", cwd)
    )
    if not queue.is_file():
        return None
    try:
        with queue.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    kept_lines: list[str] = []
    dropped_any = False
    count = 0
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            dropped_any = True
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Can't classify — keep it as-is rather than silently losing it.
            kept_lines.append(line)
            continue
        if isinstance(entry, dict) and (
            "reviewed_at" in entry or "rejected_at" in entry
        ):
            # Disposed — rotate it out of the queue.
            dropped_any = True
            continue
        if isinstance(entry, dict):
            count += 1
        kept_lines.append(line)

    if dropped_any:
        try:
            queue.write_text(
                "".join(f"{line}\n" for line in kept_lines), encoding="utf-8"
            )
        except OSError:
            pass

    if count <= 0:
        return None
    return (
        f"📋 {count} queued finding(s) from background analysis — "
        "run /session-review to review\n"
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    cwd = payload.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_dir():
        cwd = os.getcwd()

    notice = _notify_pending_findings(cwd)
    if notice is not None:
        sys.stdout.write(notice)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
