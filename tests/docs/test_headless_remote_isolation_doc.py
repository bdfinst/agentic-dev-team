"""docs/using-plugin-skills-in-the-web-environment.md must document the
headless-in-Remote isolation caveat from issue #842.

The core bug — a headless `claude -p` launched inside a Claude Code Remote
session inherits the parent's session_id and Remote-injected tool surface —
is an UPSTREAM Claude Code / Remote-runtime behavior, not fixable in this
repo. The only shippable in-repo deliverable is documenting the workaround:
run the headless benchmark harness from a plain LOCAL CLI checkout, not
nested inside a live Remote session. These content-guard sensors assert that
guidance is present in the web-environment doc.
"""

from __future__ import annotations

import pytest

from _repo_root import REPO_ROOT

DOC = REPO_ROOT / "docs" / "using-plugin-skills-in-the-web-environment.md"


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_file_exists() -> None:
    assert DOC.is_file()


def test_mentions_headless_claude_p(text: str) -> None:
    """References the headless `claude -p` harness the caveat applies to."""
    assert "claude -p" in text


def test_warns_run_from_local_checkout_not_nested_in_remote(text: str) -> None:
    """The workaround: run from a plain local CLI checkout, not nested in a
    live Claude Code Remote session."""
    lowered = text.lower()
    assert "local" in lowered
    assert "checkout" in lowered
    # The core warning must name the "not nested inside a Remote session"
    # constraint explicitly.
    assert "nested" in lowered
    assert "remote session" in lowered


def test_names_both_inheritance_symptoms(text: str) -> None:
    """Names the two tell-tale symptoms: shared session_id and the
    Remote-injected tool surface."""
    assert "session_id" in text
    assert "tool surface" in text.lower()


def test_references_isolation_recipe_precedent(text: str) -> None:
    """Points at scripts/run_tdd_experiment.py as the existing isolation
    precedent (fresh HOME/CLAUDE_CONFIG_DIR, --output-format json, no
    --resume)."""
    assert "run_tdd_experiment.py" in text


def test_notes_upstream_not_fixable_in_repo(text: str) -> None:
    """Makes clear the session-identity/tool-surface inheritance is an
    upstream Claude Code issue, not fixable in this plugin repo."""
    assert "upstream" in text.lower()
