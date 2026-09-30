"""Shared reader for `/build`'s active-state record (#2177, slice 1).

`/build` owns `.claude/memory/build-phase.json` (see `skills/build/SKILL.md`):
    {"phase": "<implement|test|refactor>", "step": "<N.M>", "written_at": "<ISO8601>",
     "test_files_staged": [], "plan_path": "<repo-relative plan file>"}

This module is the single reader of that record, so the post-compaction
re-injection hook and `/build` agree on one contract (pinned by
`tests/hooks/test_build_state_contract.py`).

"Cleared" means: the file is absent, empty, `{}`, unreadable, malformed, or
lacks a string `phase` AND a string `step`. `/build` clears the record at step
completion, so a compaction between steps yields None.

`plan_path` is taken verbatim from the record — never globbed or searched —
and is kept only when it resolves to an existing regular file inside the
project directory; otherwise it is None (phase/step are still returned).

Stdlib only; never raises (fail-open for hook callers).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Keys `/build` documents for the record; the contract test compares this to SKILL.md.
RECORD_KEYS = ("phase", "step", "written_at", "test_files_staged", "plan_path")

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


def read_active_build_state(project_dir: str | Path) -> BuildState | None:
    """Read the active build state for `project_dir`, or None when cleared."""
    try:
        root = Path(project_dir)
        data = json.loads((root / STATE_RELPATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    phase, step = data.get("phase"), data.get("step")
    if not (isinstance(phase, str) and phase and isinstance(step, str) and step):
        return None
    return BuildState(
        phase=phase,
        step=step,
        plan_path=_contained_plan_path(root, data.get("plan_path")),
    )
