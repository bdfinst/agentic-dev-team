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

import os
import shutil
import subprocess
import sys
from pathlib import Path


def project_root(start: Path | str | None = None) -> Path:
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


def _validate_segment(value: str, label: str) -> None:
    """Reject any `category`/`filename`/`subpath` component that could
    traverse outside `.claude/<category>/...`.

    pathlib does not block `..` on its own, so every caller-supplied path
    component is validated here rather than trusting each call site to do
    it. Rejects an empty string, `.`, `..`, or anything containing a path
    separator (`os.sep`/`os.altsep`) or a NUL byte.
    """
    if (
        value == ""
        or value in (".", "..")
        or os.sep in value
        or (os.altsep is not None and os.altsep in value)
        or "\0" in value
    ):
        raise ValueError(f"invalid {label}: {value!r}")


def _log_migrate_failure(legacy_path: Path, new_path: Path, exc: OSError) -> None:
    """Shared stderr diagnostic for a failed migration move (fail-open)."""
    print(
        f"[artifact_paths] failed to migrate {legacy_path} -> {new_path}: {exc}",
        file=sys.stderr,
    )


def _category_dir(name: str, root: Path | str | None = None) -> Path:
    """Return `<project-root>/.claude/<name>`. Pure path-join, no side effects."""
    _validate_segment(name, "category")
    return project_root(start=root) / ".claude" / name


def metrics_dir(root: Path | str | None = None) -> Path:
    return _category_dir("metrics", root)


def memory_dir(root: Path | str | None = None) -> Path:
    return _category_dir("memory", root)


def plans_dir(root: Path | str | None = None) -> Path:
    return _category_dir("plans", root)


def _is_git_tracked(path: Path, root: Path) -> bool:
    """True when `path` is tracked by git in the repo rooted at `root`.

    Never raises. Per AC10 ("git-tracked files are never silently moved"),
    this is the one place in this module that fails *closed*: any failure
    to invoke git (not a repo, git missing, subprocess error) is treated as
    "tracked" so the caller skips migration rather than risk silently
    moving a file that might actually be git-tracked. Every other fail-open
    behavior in this module (directory creation errors, move failures)
    stays as-is — only this error branch is inverted.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            cwd=str(root),
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return True
    return completed.returncode == 0


def resolve_file(
    category: str,
    filename: str,
    root: Path | str | None = None,
    migrate: bool = True,
) -> Path:
    """Return the `.claude/<category>/<filename>` path for a runtime artifact.

    `root` is always a walk-start passed to `project_root()`, never treated
    as a literal final directory. When `migrate` is True (the writer
    default): if a legacy `<project-root>/<category>/<filename>` exists,
    the new location does not yet exist, and the legacy file is not
    git-tracked, it is moved into place with `shutil.move` — one file at a
    time, never a directory sweep. `migrate=False` (read-only/query call
    sites) has zero filesystem side effects, including no directory
    creation.

    Fail-open: a failed move attempt logs one diagnostic line to stderr and
    is otherwise ignored — this helper never raises (except `ValueError` on
    an invalid `category`/`filename` — see `_validate_segment`).
    """
    _validate_segment(category, "category")
    _validate_segment(filename, "filename")

    base = project_root(start=root)
    new_dir = base / ".claude" / category
    new_path = new_dir / filename

    if not migrate:
        return new_path

    if new_path.exists():
        return new_path

    legacy_path = base / category / filename
    if legacy_path.is_symlink():
        return new_path
    if not legacy_path.is_file():
        return new_path

    if _is_git_tracked(legacy_path, base):
        return new_path

    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_path), str(new_path))
    except OSError as exc:
        _log_migrate_failure(legacy_path, new_path, exc)

    return new_path


def category_dir(category: str, root: Path | str | None = None) -> Path:
    """Return `<project-root>/.claude/<category>`. Pure path-join, no side effects.

    Public, generic promotion of the internal per-name accessors
    (`metrics_dir()`/`memory_dir()`/`plans_dir()`) for an arbitrary category
    string — callers join any further subpath themselves.
    """
    return _category_dir(category, root)


def migrate_dir(
    category: str,
    subpath: str,
    root: Path | str | None = None,
    exclude: set[str] | None = None,
) -> None:
    """Move every untracked file under a legacy directory tree into place.

    Walks `<project-root>/<category>/<subpath>/` (the entire subtree in one
    call, not scoped to a single slug) and moves each untracked file to the
    identical relative path under `.claude/<category>/<subpath>/`. A
    git-tracked file is left in place. A file whose basename appears in
    `exclude` is left in place even if untracked. A destination that already
    exists is left untouched (never overwritten).

    Fail-open: a failure to create a destination directory or move one file
    logs a diagnostic line to stderr and continues with the next file —
    never raises (except `ValueError` on an invalid `category`/`subpath` —
    see `_validate_segment`).
    """
    _validate_segment(category, "category")
    _validate_segment(subpath, "subpath")

    base = project_root(start=root)
    legacy_root = base / category / subpath
    if not legacy_root.is_dir():
        return

    excluded = exclude or set()
    new_root = base / ".claude" / category / subpath

    for legacy_path in legacy_root.rglob("*"):
        if legacy_path.is_symlink():
            continue
        if not legacy_path.is_file():
            continue
        if legacy_path.name in excluded:
            continue
        if _is_git_tracked(legacy_path, base):
            continue

        rel = legacy_path.relative_to(legacy_root)
        new_path = new_root / rel
        if new_path.exists():
            continue

        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_path), str(new_path))
        except OSError as exc:
            _log_migrate_failure(legacy_path, new_path, exc)


def dev_team_reports_dir(root: Path | str | None = None) -> Path:
    """Return `<project-root>/.dev-team-reports`. Pure path-join, no side effects.

    Deliberately not folded into `category_dir()`/`resolve_file()`/
    `migrate_dir()`'s `.claude/<category>` shape — the reports domain is a
    single terminal directory with no sibling to select via a `category`
    string, and no current caller needs single-filename or directory-walk
    migration semantics for it.
    """
    return project_root(start=root) / ".dev-team-reports"


__all__ = (
    "category_dir",
    "dev_team_reports_dir",
    "memory_dir",
    "metrics_dir",
    "migrate_dir",
    "plans_dir",
    "project_root",
    "resolve_file",
)
