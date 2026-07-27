"""Smoke tests for hooks/lib/pre_commit_doc_classifier.py (#1477).

The full behavioral decision-table coverage for `is_doc_only_changeset`
lives in `tests/hooks/test_pre_commit_review.py` (as
`_pcr._is_doc_only_changeset`, re-exported by `pre_commit_review.py` for
backward compatibility with that suite's existing regression tests — see
that file's own comment block for why those tests were kept in place
rather than moved). These tests just confirm the module is independently
importable and its public function behaves correctly when called directly
(not through the re-export), so the extraction itself is exercised, not
just the alias.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import pre_commit_doc_classifier as classifier  # type: ignore[import-not-found]


def test_module_exposes_is_doc_only_changeset() -> None:
    assert callable(classifier.is_doc_only_changeset)


def test_accepts_real_markdown() -> None:
    assert classifier.is_doc_only_changeset(["README.md", "docs/guide.md"]) is True


def test_rejects_code_file() -> None:
    assert classifier.is_doc_only_changeset(["a.ts"]) is False


def test_rejects_functional_config() -> None:
    assert classifier.is_doc_only_changeset(["agents/security-review.md"]) is False


def test_rejects_empty_list() -> None:
    assert classifier.is_doc_only_changeset([]) is False
