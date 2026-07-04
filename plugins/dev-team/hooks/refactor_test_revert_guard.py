#!/usr/bin/env python3
"""refactor_test_revert_guard.py — PostToolUse hook (Bash), issue #813.

The revert half of the tests-frozen-during-refactor enforcement: Bash-driven
edits bypass the PreToolUse freeze guard, so after each Bash call during a
recorded REFACTOR phase this hook restores any test file that drifted from
the staged baseline `/build` captured at the TEST→REFACTOR transition
(`git add` of the step's test files, recorded in `test_files_staged`).

- Baseline carryover (working tree matches the index) is never reverted.
- A test file dirtied after the baseline is restored via `git checkout --`.
- A test file newly created during refactor (untracked, absent from the
  baseline) is removed — no unreviewed test file is silently left in place.
- Fails OPEN on unreadable/malformed state or git failure: never reverts on
  fail-open, one audit line in `metrics/refactor-freeze.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_LIB_DIR = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from refactor_test_freeze_guard import audit  # noqa: E402
from test_file_classify import is_test_file, read_build_phase  # noqa: E402

RECOVERY = (
    "tests are frozen during REFACTOR; return to the TEST phase, make the "
    "change there, re-verify green, then re-enter REFACTOR"
)


def _git(project_dir: Path, args: List[str]) -> Optional[str]:
    """Run git in the project dir; stdout on success, None on any failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def evaluate(
    project_dir: Path, now: Optional[float] = None
) -> Tuple[int, List[str]]:
    """Return (exit_code, stdout_lines). Always exits 0 — advisory only."""
    state, error = read_build_phase(project_dir, now=now)
    if error is not None:
        audit(project_dir, "revert", "fail-open", reason=error)
        return 0, []
    if state is None or state.get("phase") != "refactor":
        return 0, []
    step = state.get("step") if isinstance(state.get("step"), str) else None
    lines: List[str] = []

    # Post-baseline drift on baseline files: the index IS the baseline.
    baseline = state.get("test_files_staged", [])
    if baseline:
        diff_out = _git(project_dir, ["diff", "--name-only", "--"] + baseline)
        if diff_out is None:
            audit(
                project_dir,
                "revert",
                "fail-open",
                step=step,
                reason="git diff against staged baseline failed",
            )
            return 0, lines
        for dirty in [f for f in diff_out.splitlines() if f.strip()]:
            restored = _git(project_dir, ["checkout", "--", dirty])
            if restored is None:
                audit(
                    project_dir,
                    "revert",
                    "fail-open",
                    file=dirty,
                    step=step,
                    reason="git checkout failed",
                )
                continue
            audit(project_dir, "revert", "revert", file=dirty, step=step)
            lines.append(
                "ADVISORY: restored test file '{}' to its TEST-phase baseline "
                "({}).".format(dirty, RECOVERY)
            )

    # Test files created during refactor: untracked and absent from baseline.
    others_out = _git(project_dir, ["ls-files", "--others", "--exclude-standard"])
    if others_out is None:
        audit(
            project_dir,
            "revert",
            "fail-open",
            step=step,
            reason="git ls-files --others failed",
        )
        return 0, lines
    for rel in [f for f in others_out.splitlines() if f.strip()]:
        candidate = project_dir / rel
        if not is_test_file(str(candidate)):
            continue
        try:
            candidate.unlink()
        except OSError as exc:
            audit(
                project_dir,
                "revert",
                "fail-open",
                file=rel,
                step=step,
                reason="could not remove: {}".format(exc),
            )
            continue
        audit(project_dir, "revert", "remove", file=rel, step=step)
        lines.append(
            "ADVISORY: removed test file '{}' created during REFACTOR "
            "({}).".format(rel, RECOVERY)
        )
    return 0, lines


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    try:
        # Payload is unused — the guard inspects disk state — but stdin must
        # be drained so the hook runner never blocks on a full pipe.
        sys.stdin.read()
    except OSError:
        pass
    try:
        exit_code, lines = evaluate(project_dir)
    except Exception as exc:  # fail open — never revert, never block
        audit(project_dir, "revert", "fail-open", reason="internal error: {}".format(exc))
        return 0
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
