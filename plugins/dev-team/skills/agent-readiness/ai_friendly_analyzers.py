"""AI-friendly repository analyzers for the agent-readiness scanner (issue #2178).

Sibling of scanner.py: one pure function per new `mvp: true` criterion, each
`(root, cfg) -> {score, max, evidence}`. Rubric and evidence anchors live in
`knowledge/ai-friendly-repo-guidelines.md`. Stdlib-only. Thresholds come from
scorecard.yaml (read with `.get()` defaults); nothing here hardcodes scoring
policy beyond a safe fallback when a key is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

GUIDE = "knowledge/ai-friendly-repo-guidelines.md"

# --------------------------------------------------------------------------
# Shared, pruned, memoized directory walk (one traversal per scan).
# --------------------------------------------------------------------------

_WALK_CACHE: dict[tuple[str, tuple[str, ...]], list[tuple[Path, list[str]]]] = {}


def reset_walk_cache() -> None:
    """Drop memoized walks; scan() calls this so repeated scans see fresh state."""
    _WALK_CACHE.clear()


def walk_tree(root: Path, exclude_dirs) -> list[tuple[Path, list[str]]]:
    """Return [(dirpath, filenames)] under root, pruning excluded dirs.

    Never follows directory symlinks (so symlink loops terminate). Sorted for
    deterministic output. Memoized per (root, exclude set) until reset.
    """
    excl = tuple(sorted(set(exclude_dirs or ())))
    key = (str(root), excl)
    hit = _WALK_CACHE.get(key)
    if hit is not None:
        return hit
    excl_set = set(excl)
    out: list[tuple[Path, list[str]]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel == "." else rel + "/"
        # An entry prunes by bare dir name (".git") or root-relative path
        # (".claude/worktrees").
        dirnames[:] = sorted(
            d for d in dirnames if d not in excl_set and prefix + d not in excl_set
        )
        out.append((Path(dirpath), sorted(filenames)))
    _WALK_CACHE[key] = out
    return out


def walk_files(root: Path, exclude_dirs):
    """Yield every file Path under root, honoring the pruned walk."""
    for dirpath, filenames in walk_tree(root, exclude_dirs):
        for name in filenames:
            yield dirpath / name


def _score(n: int, evidence: str) -> dict:
    return {"score": n, "max": 2, "evidence": evidence}


# Populated by later slices; merged into scanner.ANALYZERS.
AI_FRIENDLY_ANALYZERS: dict = {}
