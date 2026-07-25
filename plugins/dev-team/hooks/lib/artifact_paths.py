"""artifact_paths — shared project-root resolution for runtime artifacts.

Part of the `.claude/`-scoped runtime artifact migration (issue #1406 /
plan `opt-in-metrics-and-claude-scoped-artifacts.md`, Slice 4). Provides a
single, git-aware resolution of "the project root" so every hook/script
that writes a runtime artifact (metrics, memory, plans) agrees on where
that root is — instead of each hook independently trusting
`CLAUDE_PROJECT_DIR` (can be unset or stale) or a bare relative path
(resolves against whatever the process's real OS cwd happens to be, which
disagrees with the project root when a hook is invoked from a
subdirectory).

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def project_root(start: "Path | str | None" = None) -> Path:
    """Return the project root, resolved via `git rev-parse --show-toplevel`.

    `start` is the directory to resolve from (defaults to the current
    process's OS cwd). On any failure to resolve a git root — not a repo,
    `git` not installed, non-zero exit, empty output — falls back to
    `start` (or cwd) itself. Never raises.
    """
    begin = Path(start) if start is not None else Path.cwd()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(begin),
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return begin
    if completed.returncode != 0:
        return begin
    output = completed.stdout.strip()
    if not output:
        return begin
    return Path(output)


def _category_dir(name: str, root: "Path | str | None" = None) -> Path:
    """Return `<project-root>/.claude/<name>`. Pure path-join, no side effects."""
    return project_root(start=root) / ".claude" / name


def metrics_dir(root: "Path | str | None" = None) -> Path:
    return _category_dir("metrics", root)


def memory_dir(root: "Path | str | None" = None) -> Path:
    return _category_dir("memory", root)


def plans_dir(root: "Path | str | None" = None) -> Path:
    return _category_dir("plans", root)


__all__ = (
    "project_root",
    "metrics_dir",
    "memory_dir",
    "plans_dir",
)
