#!/usr/bin/env python3
"""detect_bdd_convention.py — detect a target project's BDD convention.

Deterministic probe `/plan` shells to at plan-creation time (issue #537),
reporting where derived .feature files should land:

    {"signal": "feature-files" | "manifest" | "none",
     "framework": <name or null>,
     "dir": <repo-relative destination or null>}

Precedence: existing .feature files > BDD dependency in a manifest > none.
Detection is conservative — a false negative (no signal, which prompts the
operator) is preferred over a false positive (the wrong directory), so any
ambiguity (multiple unrelated .feature roots) reports "none". Vendored and
generated trees (node_modules/, vendor/, dist/, build/, .git/, virtualenvs)
are never treated as a signal.

Stdlib-only. Python 3.8+. See docs/specs/plan-gherkin-feature-persistence.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, List, Optional

# Trees whose contents are a dependency's (or a build's), never the project's
# own convention.
VENDORED_DIR_NAMES = frozenset({".git", "node_modules", "vendor", "dist", "build"})

# Presence of this file marks a directory as a virtualenv, whatever its name.
_VIRTUALENV_MARKER = "pyvenv.cfg"


def _is_vendored_dir(directory: Path) -> bool:
    """True for vendored/generated trees the scan must never treat as signal."""
    if directory.name in VENDORED_DIR_NAMES:
        return True
    return (directory / _VIRTUALENV_MARKER).is_file()


def _iter_project_files(root: Path) -> Iterator[Path]:
    """Yield the project's own files under `root`, pruning vendored trees."""
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in sorted(directory.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if not _is_vendored_dir(entry):
                    pending.append(entry)
            elif entry.is_file():
                yield entry


def _common_directory(paths: Iterable[Path]) -> Path:
    """Longest common ancestor of relative paths ('.' when they share none)."""
    common: List[str] = []
    for components in zip(*(p.parts for p in paths)):
        if len(set(components)) != 1:
            break
        common.append(components[0])
    return Path(*common) if common else Path(".")


def scan_feature_dir(root: Path) -> Optional[str]:
    """Repo-relative common directory of the project's .feature files.

    None when no .feature file exists outside vendored trees, or when the
    files' common ancestor is the project root itself — which covers both
    multiple unrelated roots and root-level orphans (conservative: prompt
    rather than guess).
    """
    parents = sorted(
        {
            found.parent.relative_to(root)
            for found in _iter_project_files(root)
            if found.suffix == ".feature"
        }
    )
    if not parents:
        return None
    common = _common_directory(parents)
    if common == Path("."):
        return None
    return common.as_posix()


def detect(root: Path) -> dict:
    """Detection result {signal, framework, dir} for the project at `root`."""
    feature_dir = scan_feature_dir(root)
    if feature_dir is not None:
        return {"signal": "feature-files", "framework": None, "dir": feature_dir}
    return {"signal": "none", "framework": None, "dir": None}
