#!/usr/bin/env python3
"""Classify a changeset's shape to gate low-yield review lenses (#1254).

Running the full review panel unconditionally wastes tokens on diffs with no
runtime/logic surface. The 2026-07-20 audit found `performance-review` fired
0/10 and `correctness-review` 1/10 — on doc/config-dominated commits most lenses
no-op. `/code-review` (invoked directly) applies no complexity gate the way
`/build` and `/plan` do, so every lens runs on every changed file regardless of
change shape.

This module is the deterministic gate. Given the changed-file list it decides
whether the changeset has any **runtime surface** — a file that could hold
executable logic. When it does not (every file is documentation or config),
the two low-yield code lenses (`performance-review`, `correctness-review`) are
skipped; the rest of the panel still runs.

**Fail-safe by construction.** A file is "no runtime surface" only when it is
*provably* documentation or config (matches an explicit allowlist). Anything
else — an unknown extension, a source file, functional Claude-config markdown —
counts as runtime surface, so the lenses run. A misclassification can only ever
*add* a lens, never silently drop one on real code.

Pure policy — no filesystem, no globals. Mirrors the documentation-only
short-circuit's classification in `code-review/SKILL.md` (this gate is the
weaker sibling: the short-circuit skips *everything* when every file is
documentation; this skips only the two low-yield lenses when every file is
documentation *or* config, which the doc-only short-circuit does not cover).

Scope note: this is a filename-shape gate. Annotation-only edits *inside* a
source file (e.g. adding a C# attribute) still count as runtime surface — that
would require diff parsing and is deliberately out of scope for v1.

Shared literal tables (#1477): the documentation-extension, doc-root-word,
and functional-config-name/segment literals below are byte-identical to
`hooks/pre_commit_review.py`'s own doc-only classifier and were previously
hand-duplicated between the two, kept in sync only by comment convention.
They now live in `hooks/lib/doc_classification.py`, imported here via the
same `sys.path.insert` cross-boundary pattern `pre_commit_review.py` already
uses for its own `hooks/lib/` imports — see that module's docstring for why
this location was chosen and why the *matching logic* (prefix vs. exact
match) intentionally stays local to each caller rather than being unified
too.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
# -> hooks/lib
_HOOKS_LIB_DIR = Path(__file__).resolve().parents[3] / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    from doc_classification import (  # type: ignore[import-not-found]
        DOC_EXTENSIONS,
        DOC_ROOT_WORDS,
        is_functional_config,
    )
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    DOC_EXTENSIONS = frozenset({".md", ".mdx", ".markdown", ".rst", ".txt", ".adoc"})
    DOC_ROOT_WORDS = (
        "readme", "changelog", "contributing", "license", "notice",
        "authors", "code_of_conduct",
    )
    _FALLBACK_FUNCTIONAL_CONFIG_NAMES = frozenset({"claude.md", "agents.md"})
    _FALLBACK_FUNCTIONAL_CONFIG_SEGMENTS = frozenset(
        {".claude", "agents", "skills", "prompts", "knowledge", "templates"}
    )

    def is_functional_config(file_path: str) -> bool:
        path = PurePosixPath(file_path)
        if path.name.lower() in _FALLBACK_FUNCTIONAL_CONFIG_NAMES:
            return True
        return any(seg in _FALLBACK_FUNCTIONAL_CONFIG_SEGMENTS for seg in path.parts)

# The lenses this gate can skip. Both are code-only lenses that no-op on diffs
# with no executable logic to reason about.
LOW_YIELD_LENSES = ["performance-review", "correctness-review"]

# Documentation extensions (lower-cased). Mirrors SKILL.md's doc-only rule.
_DOC_EXTENSIONS = DOC_EXTENSIONS

# Documentation root-file stems (matched case-insensitively on the stem
# prefix) — same word list `pre_commit_review.py`'s doc-only classifier uses
# for its own (exact-match) root-doc check.
_DOC_ROOT_PREFIXES = DOC_ROOT_WORDS

# Config / data extensions with no executable logic surface (lower-cased).
# Unique to this gate — `pre_commit_review.py` has no equivalent "config"
# concept, so this stays local (nothing to extract against).
_CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".properties", ".lock", ".csv", ".tsv",
}

# Config dotfiles carry no suffix (``PurePosixPath(".gitignore").suffix == ""``),
# so they are matched by full name instead (lower-cased).
_CONFIG_NAMES = {
    ".gitignore", ".gitattributes", ".editorconfig", ".env", ".dockerignore",
    ".npmignore", ".prettierignore",
}

# Functional-config classification (markdown/paths that drive agent/skill/
# command behavior and always count as runtime surface, same exclusion as
# SKILL.md) now lives in `is_functional_config` above — shared with
# `select_lenses.py` (#1923), including the "templates" addition this gate
# has always applied on top of the shared core set (`pre_commit_review.py`'s
# doc-only classifier deliberately does not include it; see that module's
# docstring on staying a strict subset — unaffected by this extraction).


def _is_documentation(path: PurePosixPath) -> bool:
    if path.suffix.lower() in _DOC_EXTENSIONS:
        return True
    if "docs" in path.parts:
        return True
    stem = path.name.lower()
    return any(stem.startswith(prefix) for prefix in _DOC_ROOT_PREFIXES)


def _is_config(path: PurePosixPath) -> bool:
    return (
        path.suffix.lower() in _CONFIG_EXTENSIONS
        or path.name.lower() in _CONFIG_NAMES
    )


def _has_runtime_surface_file(file: str) -> bool:
    """True when a single file could hold executable logic (fail-safe default)."""
    path = PurePosixPath(str(file).strip())
    if not path.name:
        return False  # empty entry contributes nothing
    if is_functional_config(path):
        return True
    # Provably non-runtime only when documentation or config; anything else
    # (source, unknown extension) is treated as runtime surface.
    return not (_is_documentation(path) or _is_config(path))


def has_runtime_surface(files: Iterable[str]) -> bool:
    """True when *any* changed file could hold executable logic.

    An empty changeset has no runtime surface (returns False).
    """
    return any(_has_runtime_surface_file(f) for f in files if str(f).strip())


def lenses_to_skip(files: Iterable[str]) -> list[str]:
    """Return the low-yield lenses to skip for this changeset.

    Empty when the changeset has any runtime surface (run every lens). Otherwise
    the doc/config-only changeset skips `performance-review` and
    `correctness-review`.
    """
    file_list = [f for f in files if str(f).strip()]
    if not file_list:
        return []  # nothing to review — the caller handles empty scope
    return [] if has_runtime_surface(file_list) else list(LOW_YIELD_LENSES)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--files", nargs="*", default=[],
        help="changed file paths (space-separated)",
    )
    parser.add_argument(
        "--files-from", default=None,
        help="read newline-separated file paths from this file ('-' for stdin)",
    )
    args = parser.parse_args(argv)

    files = list(args.files)
    if args.files_from:
        if args.files_from == "-":
            text = sys.stdin.read()
        else:
            with open(args.files_from) as f:
                text = f.read()
        files.extend(line for line in text.splitlines() if line.strip())

    skip = lenses_to_skip(files)
    result = {
        "hasRuntimeSurface": has_runtime_surface(files),
        "skipLenses": skip,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
