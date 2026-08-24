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

Test-only classification (#1964)
--------------------------------
This module answers a second, independent question: is *every* changed file
provably a test file (per `knowledge/test-file-indicators.md`)? A diff of that
shape is structurally incapable of exhibiting what several expensive lenses
look for — and under `/test-improve`'s default `refactor-mode: no-refactor`,
Phase 5's diff is *guaranteed* to have it, because `/build` rejects
production-code changes in that mode.

`testOnly` is reported but currently skips **nothing**: `TEST_ONLY_SKIP_LENSES`
ships empty on purpose. Which lens is safe to drop on a test-only diff is an
empirical question, and the evidence (per-lens outcomes split by `diff_shape`
in `review-value.jsonl`) is still being collected. This mirrors the
architectural-impact gate's own rule — "widen `GATED_LENSES` from #1624's
measured per-agent data, not from intuition about which lens probably no-ops."
Two lenses in particular must NOT be added without data: `security-review`
(tests embed credentials and injection payloads) and `correctness-review`
(an inverted assertion is precisely its subject).

Test-only classification is **include-biased in the same direction** as the
runtime-surface check: a changeset is test-only only when every file is
*provably* a test. Anything unproven — a fixture, a `conftest.py`, a helper, a
`.cs` file whose test-ness needs its contents — makes the answer `False`, so
the full panel runs. Because this module is filesystem-free by contract, the
content-probing branches of the shared classifier are deliberately starved
(`content=""`), which can only ever move the answer toward "not test-only".

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
import re
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

# `knowledge/test-file-indicators.md`'s single encoding, shared with the
# refactor test-freeze guards (#1964) — same cross-boundary import pattern as
# `doc_classification` above. Never re-implement the indicator list here: a
# second copy is exactly what the #1477 extraction removed for the doc tables.
try:
    from test_file_classify import is_test_file  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    # Case-sensitivity is load-bearing and mirrors test_file_classify's own
    # compilation flags exactly. The JS/TS, Python, and .feature indicators are
    # case-INsensitive there; the step-definition indicator is case-SENSITIVE.
    # Folding all four into one IGNORECASE pattern reads `backsteps.py` and
    # `mysteps.js` as step definitions, which would let an ordinary source file
    # pass as a test and over-claim `test-only` — the one direction this
    # module's include-bias must never fail in.
    _FALLBACK_TEST_NAME_RE = re.compile(
        r"(\.(test|spec)\.[^./]+$"          # JS/TS  foo.test.ts
        r"|^(test_.+|.+_test)\.py$"          # Python test_foo.py / foo_test.py
        r"|\.feature$)",                     # Gherkin
        re.IGNORECASE,
    )
    _FALLBACK_STEP_DEF_RE = re.compile(  # deliberately NOT IGNORECASE
        r"(\.steps\.[^./]+$|StepDefinitions\.[^./]+$|Steps\.[^./]+$)"
    )

    def is_test_file(path: str, content: str | None = None) -> bool:
        p = PurePosixPath(str(path))
        if not p.name:
            return False
        if _FALLBACK_TEST_NAME_RE.search(p.name):
            return True
        if _FALLBACK_STEP_DEF_RE.search(p.name):
            return True
        if "__tests__" in p.parts:
            return True
        # Java class-name convention; C# needs contents we deliberately don't read.
        return p.suffix.lower() == ".java" and p.stem.endswith(
            ("Test", "Tests", "TestCase", "Spec")
        )

# The lenses this gate can skip. Both are code-only lenses that no-op on diffs
# with no executable logic to reason about.
LOW_YIELD_LENSES = ["performance-review", "correctness-review"]

# Lenses to skip when EVERY changed file is provably a test file (#1964).
# Deliberately EMPTY until per-lens `diff_shape` outcome data justifies each
# entry — see this module's docstring. Adding a name here without citing that
# measurement is the mistake the docstring names; `security-review` and
# `correctness-review` are explicitly not candidates on intuition.
TEST_ONLY_SKIP_LENSES: list[str] = []

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


def _is_provably_test_file(file: str) -> bool:
    """True when a single file is provably a test (fail-safe default: False).

    `content=""` starves the shared classifier's content-probing branches (C#
    attributes, Java annotations) rather than touching the filesystem, keeping
    this module's no-I/O contract. That can only ever answer "not a test",
    which biases the changeset toward "not test-only" — i.e. toward running
    every lens. Java's class-name convention (`FooTest.java`) still resolves
    by name and is unaffected.
    """
    name = str(file).strip()
    if not name:
        return False
    return bool(is_test_file(name, content=""))


def is_test_only(files: Iterable[str]) -> bool:
    """True when *every* changed file is provably a test file.

    An empty changeset is not test-only (there is nothing to prove), matching
    `has_runtime_surface`'s treatment of the empty case.
    """
    file_list = [f for f in files if str(f).strip()]
    if not file_list:
        return False
    return all(_is_provably_test_file(f) for f in file_list)


def lenses_to_skip(files: Iterable[str]) -> list[str]:
    """Return the low-yield lenses to skip for this changeset.

    Empty when the changeset has any runtime surface (run every lens). Otherwise
    the doc/config-only changeset skips `performance-review` and
    `correctness-review`.
    """
    file_list = [f for f in files if str(f).strip()]
    if not file_list:
        return []  # nothing to review — the caller handles empty scope
    if not has_runtime_surface(file_list):
        return list(LOW_YIELD_LENSES)
    # Runtime surface present. A test-only changeset may still narrow the
    # roster once TEST_ONLY_SKIP_LENSES is populated from measured data; it is
    # empty today, so this returns [] and the full panel runs (#1964).
    if is_test_only(file_list):
        return list(TEST_ONLY_SKIP_LENSES)
    return []


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
        "isTestOnly": is_test_only(files),
        "skipLenses": skip,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
