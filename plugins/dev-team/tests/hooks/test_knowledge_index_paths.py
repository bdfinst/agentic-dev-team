"""Unit tests for hooks/lib/knowledge_index_paths.py (#575 / #572 Cluster A).

Behavior parity with the .sh sibling at hooks/lib/knowledge-index-paths.sh
is what this port owes; the tests below mirror the shape of the existing
bats suite (tests/hooks/knowledge_index_paths_tests.bats) one-for-one so a
future author reading either can trust they agree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import knowledge_index_paths as paths  # type: ignore[import-not-found]

# --- module surface --------------------------------------------------------


def test_module_exposes_corpus_regex_and_is_corpus_path() -> None:
    assert isinstance(paths.CORPUS_REGEX, str)
    assert paths.CORPUS_REGEX
    assert callable(paths.is_corpus_path)


def test_corpus_regex_is_valid_python_regex() -> None:
    re.compile(paths.CORPUS_REGEX)


# --- matches ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "plugins/dev-team/knowledge/owasp-detection.md",
        "plugins/dev-team/knowledge/agent-registry.md",
        "plugins/dev-team/skills/specs/SKILL.md",
        "plugins/dev-team/skills/mutation-testing/SKILL.md",
        # Absolute / repo-parent-prefixed paths must still match — the .sh
        # regex allows an optional leading "(^|/)" segment.
        "/abs/root/plugins/dev-team/knowledge/owasp-detection.md",
        "/abs/root/plugins/dev-team/skills/plan/SKILL.md",
        # references/*.md — spliced into a SKILL.md summary via include
        # markers (build_knowledge_index.py), so it must be in-corpus too.
        "plugins/dev-team/skills/test-improve/references/phase-5-improve.md",
        "/abs/root/plugins/dev-team/skills/test-improve/references/review-loop.md",
    ],
)
def test_is_corpus_path_matches_corpus_files(path: str) -> None:
    assert paths.is_corpus_path(path) is True


# --- rejections ------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        # schemas/ subtree is out of scope
        "plugins/dev-team/knowledge/schemas/foo.json",
        "plugins/dev-team/knowledge/schemas/notes.md",
        # neighboring plugin dirs
        "plugins/dev-team/agents/security-review.md",
        "plugins/dev-team/commands/code-review.md",
        "plugins/dev-team/docs/agent-architecture.md",
        # non-markdown corpus paths
        "plugins/dev-team/knowledge/index.json",
        # unrelated repo paths
        "README.md",
        "plans/foo.md",
        # a SKILL.md nested one level too deep is not the anchor
        "plugins/dev-team/skills/specs/nested/SKILL.md",
        # a references/*.md file nested one level too deep is not the anchor
        "plugins/dev-team/skills/specs/references/nested/detail.md",
        # non-markdown references/ file
        "plugins/dev-team/skills/specs/references/detail.json",
        # empty / degenerate
        "",
    ],
)
def test_is_corpus_path_rejects_non_corpus(path: str) -> None:
    assert paths.is_corpus_path(path) is False


# --- regex ↔ predicate agreement -------------------------------------------


@pytest.mark.parametrize(
    "path,expect_match",
    [
        ("plugins/dev-team/knowledge/owasp-detection.md", True),
        ("plugins/dev-team/skills/specs/SKILL.md", True),
        ("plugins/dev-team/knowledge/schemas/foo.md", False),
        ("plugins/dev-team/agents/security-review.md", False),
    ],
)
def test_corpus_regex_agrees_with_is_corpus_path(path: str, expect_match: bool) -> None:
    """The exported CORPUS_REGEX and the predicate must classify identically —
    the .sh contract is that a shell caller using `grep -E "$CORPUS_REGEX"`
    and a shell caller using `_is_corpus_path` see the same paths."""
    matched = bool(re.search(paths.CORPUS_REGEX, path))
    assert matched is expect_match
    assert matched is paths.is_corpus_path(path)


# --- Windows path inputs ---------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        # A Windows-native (backslash) path is not the shape callers pass — the
        # .sh uses / everywhere — but the port must not crash on such input.
        "C:\\repo\\plugins\\dev-team\\knowledge\\owasp-detection.md",
        # Git Bash surfaces forward-slash paths even on Windows, so this must
        # still match:
        "C:/repo/plugins/dev-team/knowledge/owasp-detection.md",
    ],
)
def test_is_corpus_path_windows_inputs(path: str) -> None:
    # Backslash form must NOT match (the corpus is a forward-slash convention).
    # Forward-slash form MUST match — Git Bash normalizes to /.
    expected = "\\" not in path
    assert paths.is_corpus_path(path) is expected


# --- filter_corpus_paths (convenience for hook callers) --------------------


def test_filter_corpus_paths_returns_only_corpus_items_in_order() -> None:
    inputs = [
        "plugins/dev-team/knowledge/owasp-detection.md",
        "README.md",
        "plugins/dev-team/skills/specs/SKILL.md",
        "plugins/dev-team/agents/security-review.md",
        "plugins/dev-team/knowledge/schemas/foo.md",
        "plugins/dev-team/knowledge/agent-registry.md",
    ]
    got = paths.filter_corpus_paths(inputs)
    assert got == [
        "plugins/dev-team/knowledge/owasp-detection.md",
        "plugins/dev-team/skills/specs/SKILL.md",
        "plugins/dev-team/knowledge/agent-registry.md",
    ]


def test_filter_corpus_paths_handles_empty_and_none() -> None:
    assert paths.filter_corpus_paths([]) == []
