"""Shared reader for `/build`'s active-state record (#2177, slice 1).

`/build` owns `.claude/memory/build-phase.json` (see `skills/build/SKILL.md`):
    {"phase": "<implement|test|refactor|between-steps>", "step": "<N.M>", "written_at": "<ISO8601>",
     "test_files_staged": [], "plan_path": "<repo-relative plan file>"}

This module is the single reader of that record, so the post-compaction
re-injection hook and `/build` agree on one contract (pinned by
`tests/hooks/test_build_state_contract.py`).

"Cleared" means: the file is absent, empty, `{}`, unreadable, malformed, or
lacks a string `phase` AND a string `step`. `/build` clears the record only when
the plan completes. At each step completion it rewrites it as a `between-steps`
record (`phase == BETWEEN_STEPS`, `step` = the next step, same `plan_path`), so a
compaction between steps still restores the plan and next step. Only the
`refactor` phase is enforced by the guards, so the retained record is inert to
them, and an old one is ignored by the same staleness rule below.

A record whose `written_at` is missing/unparseable, or older than
`STALE_AFTER_SECONDS` (shared with `test_file_classify.py`: a crashed `/build`
must not haunt later sessions), is also treated as cleared.

`plan_path` is taken verbatim from the record — never globbed or searched —
and is kept only when it resolves to an existing regular file inside the
project directory; otherwise it is None (phase/step are still returned).

Stdlib only; never raises (fail-open for hook callers).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from test_file_classify import STALE_AFTER_SECONDS  # same staleness rule as the guards

#: Keys `/build` documents for the record; the contract test compares this to SKILL.md.
RECORD_KEYS = ("phase", "step", "written_at", "test_files_staged", "plan_path")

#: `phase` value `/build` writes at step completion in place of deleting the file.
BETWEEN_STEPS = "between-steps"

STATE_RELPATH = Path(".claude") / "memory" / "build-phase.json"


@dataclass(frozen=True)
class BuildState:
    phase: str
    step: str
    plan_path: str | None


def _contained_plan_path(project_dir: Path, raw: object) -> str | None:
    """Return `raw` when it names a regular file inside `project_dir`."""
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        return None
    try:
        root = project_dir.resolve()
        candidate = (root / raw).resolve()
        candidate.relative_to(root)
        if not candidate.is_file():
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return raw


def _parse_written_at(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def read_active_build_state(
    project_dir: str | Path, now: float | None = None
) -> BuildState | None:
    """Read the active build state for `project_dir`, or None when cleared/stale.

    `now` is the injectable clock (epoch seconds) for staleness tests.
    """
    try:
        root = Path(project_dir)
        data = json.loads((root / STATE_RELPATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError, RuntimeError):
        return None
    if not isinstance(data, dict):
        return None
    phase, step = data.get("phase"), data.get("step")
    if not (isinstance(phase, str) and phase and isinstance(step, str) and step):
        return None
    written_at = _parse_written_at(data.get("written_at"))
    if written_at is None:
        return None
    if (time.time() if now is None else now) - written_at > STALE_AFTER_SECONDS:
        return None
    return BuildState(
        phase=phase,
        step=step,
        plan_path=_contained_plan_path(root, data.get("plan_path")),
    )
