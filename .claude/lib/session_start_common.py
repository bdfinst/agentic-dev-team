#!/usr/bin/env python3
"""Shared plumbing for the repo-root ``.claude/*.py`` SessionStart hooks.

``ensure_npm_ci.py`` and ``ensure_code_graph_tools.py`` (issue #1469) both
need the project root and both run one-off, time-boxed, fail-open
subprocess calls with their combined output logged to a file rather than
captured into the process (npm/tool output can carry registry tokens or
absolute paths that shouldn't land in the SessionStart context a model
reads). Factored out here — mirroring the ``plugins/dev-team/hooks/lib/``
convention — so the two hooks share one implementation instead of
drifting (structure-review finding on #1469).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def resolve_project_root() -> Path:
    """``$CLAUDE_PROJECT_DIR`` if set, else the repo root, found by walking
    up from this module's own location to the ``.claude`` directory and
    returning its parent. Anchored on the ``.claude`` directory name
    (rather than a fixed parent-count) so it stays correct regardless of
    which hook calls it or where this module lives under ``.claude/``."""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == ".claude":
            return parent.parent
    return here.parents[2]


def run_logged(cmd: list, cwd: Path, log_path: Path, timeout_seconds: int) -> bool:
    """Run a command, time-boxed, with combined stdout/stderr written to
    ``log_path`` instead of captured into this process — so failure detail
    stays available for a human to inspect (a caller's message can point at
    ``log_path``) without embedding potentially sensitive command output
    into the SessionStart context. Returns True on a zero exit; False on a
    nonzero exit, a timeout, or any OSError launching the command — never
    raises."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


__all__ = ("resolve_project_root", "run_logged")
