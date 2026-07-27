"""Unit tests for hooks/lib/doc_classification.py (#1477).

The shared literal tables extracted out of `pre_commit_doc_classifier.py`
and `skills/code-review/scripts/change_shape.py` — this module carries no
logic, only the data both callers agree on. These tests pin the literal
values themselves so a future accidental edit to one entry is caught here,
independent of either caller's own behavioral tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import doc_classification as dc  # type: ignore[import-not-found]


def test_doc_extensions_matches_both_callers_prior_values() -> None:
    assert dc.DOC_EXTENSIONS == frozenset(
        {".md", ".mdx", ".markdown", ".rst", ".txt", ".adoc"}
    )


def test_doc_root_words_matches_both_callers_prior_values() -> None:
    assert set(dc.DOC_ROOT_WORDS) == {
        "readme", "changelog", "contributing", "license", "notice",
        "authors", "code_of_conduct",
    }
    # Exactly 7 words, no accidental duplicates.
    assert len(dc.DOC_ROOT_WORDS) == 7


def test_functional_config_names_matches_both_callers_prior_values() -> None:
    assert dc.FUNCTIONAL_CONFIG_NAMES == frozenset({"claude.md", "agents.md"})


def test_core_functional_config_segments_excludes_templates() -> None:
    """`"templates"` is deliberately NOT in the shared core set — it's
    `change_shape.py`'s own addition layered on top (see that module's
    comment); `pre_commit_doc_classifier.py` uses the core set unmodified."""
    assert dc.CORE_FUNCTIONAL_CONFIG_SEGMENTS == frozenset(
        {".claude", "agents", "skills", "prompts", "knowledge"}
    )
    assert "templates" not in dc.CORE_FUNCTIONAL_CONFIG_SEGMENTS
