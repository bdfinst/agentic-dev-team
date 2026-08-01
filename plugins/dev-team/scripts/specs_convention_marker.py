#!/usr/bin/env python3
"""Detect the issue-first specs convention opt-in marker (#986).

`/specs` only persists spec artifacts to a GitHub issue (instead of writing
`docs/specs/<slug>.md`) on a project that has *explicitly* opted into that
convention. This script classifies whether a project's root `CLAUDE.md`
declares the opt-in via a literal marker phrase, so no downstream consumer of
the shipped plugin is silently switched to issue-based persistence just
because its origin happens to be GitHub.

Prints exactly one of:
    marker     — root CLAUDE.md exists and contains the marker phrase
                 ("Specs and plans are GitHub issues here, not files",
                 markdown emphasis stripped, case-insensitive)
    no-marker  — root CLAUDE.md exists but does not contain the marker phrase
    none       — no root CLAUDE.md found (fail-open: callers treat this
                 identically to "no-marker" — routes to file-based
                 persistence — never blocks)

This is the primary, literal-match, tested path. A caller MAY still apply
judgment for an equivalently-worded-but-differently-phrased declaration
before concluding "no marker" when this script reports `no-marker` or
`none` — that manual-judgment fallback is deliberately not covered by this
script or its tests (see plans/issue-986-specs-github-issue-persistence.md's
Risks & Open Questions).

Reads `<repo-root>/CLAUDE.md` (repo root resolved via
`git rev-parse --show-toplevel`) unless a path is given as argv[1] (for
testing, or to point at an arbitrary CLAUDE.md directly).

Usage: specs_convention_marker.py [claude-md-path]

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MARKER_PHRASE = "specs and plans are github issues here, not files"


def has_marker(text: str) -> bool:
    """Return True if `text` contains the issue-first-specs marker phrase.

    Strips markdown emphasis characters (`*`) and lowercases before matching,
    so "**Specs and plans are GitHub issues here, not files.**" and other
    minor emphasis/case variants still match.
    """
    if not text:
        return False
    normalized = text.replace("*", "").lower()
    return MARKER_PHRASE in normalized


def classify(claude_md_path: Path | None) -> str:
    """Return "marker", "no-marker", or "none" for a root CLAUDE.md path.

    Fail-open: any read error (missing file, permission error, etc.) yields
    "none" rather than raising.
    """
    if claude_md_path is None:
        return "none"
    try:
        if not claude_md_path.is_file():
            return "none"
        text = claude_md_path.read_text(encoding="utf-8")
    except OSError:
        return "none"
    return "marker" if has_marker(text) else "no-marker"


def _resolve_repo_root() -> Path | None:
    """Return the git repo root, or None on any failure (fail-open)."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return Path(root) if root else None


def main(argv: list) -> int:
    if len(argv) > 1 and argv[1]:
        claude_md_path: Path | None = Path(argv[1])
    else:
        root = _resolve_repo_root()
        claude_md_path = (root / "CLAUDE.md") if root is not None else None
    print(classify(claude_md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
