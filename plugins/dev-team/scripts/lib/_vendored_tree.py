"""scripts/lib/_vendored_tree.py — shared vendored/generated-directory
pruning helper.

Extracted (issue #1420) from `detect_bdd_convention.py` and
`gherkin_stub_gate.py`, which each carried a byte-for-byte-identical copy of
this logic. A third caller (`gherkin_failure_path_gate.py`) made the
duplication the third occurrence — the threshold where it becomes a shared
helper rather than a per-script judgment call. Lives under `scripts/lib/`,
per this repo's established shared-helper convention (see `plan_parse.py`
and its callers) — each of the three callers above resolves this directory
onto `sys.path` via `sys.path.insert(0, str(Path(__file__).resolve().parent
/ "lib"))` before importing it.

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

# Trees whose contents are a dependency's (or a build's), never the project's
# own convention/surface.
VENDORED_DIR_NAMES = frozenset({".git", "node_modules", "vendor", "dist", "build"})

# Presence of this file marks a directory as a virtualenv, whatever its name.
_VIRTUALENV_MARKER = "pyvenv.cfg"


def is_vendored_dir(directory: Path) -> bool:
    """True for vendored/generated trees a scan must never walk into or
    treat as project signal."""
    if directory.name in VENDORED_DIR_NAMES:
        return True
    return (directory / _VIRTUALENV_MARKER).is_file()


def iter_files(root: Path) -> Iterator[Path]:
    """Yield files under `root`, pruning vendored trees and symlinks. This
    skips a symlinked *file* as well as a symlinked directory — a scan must
    never grep the same underlying file twice under two different paths,
    and never loop forever chasing a symlink cycle a directory-only check
    wouldn't catch."""
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in sorted(directory.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir() and not is_vendored_dir(entry):
                pending.append(entry)
            elif entry.is_file():
                yield entry


def find_files(directories: list, predicate) -> list:
    """Return every file under `directories` for which `predicate(path)` is
    true, pruning vendored trees via `iter_files`, sorted for deterministic
    output. Shared by `gherkin_failure_path_gate.py` and
    `gherkin_stub_gate.py`, whose directory-scan-and-filter functions were
    structurally identical apart from the filter predicate (differing only
    in which file extensions they cared about)."""
    found = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in iter_files(directory):
            if predicate(path):
                found.append(path)
    return sorted(set(found))
