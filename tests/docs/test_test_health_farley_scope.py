"""Regression guard for #533: /test-health must pass its --path through
to /test-design explicitly and render the scope label in its Output
block, so a subtree audit never inherits a whole-repo score.

Ported from tests/docs/test_health_farley_scope_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-health" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_documents_scoped_test_design_invocation_with_metavariable(
    text: str,
) -> None:
    # Require the templated form '/test-design --path <dir>' (or a
    # ${var}-style substitution), not just the bare substring.
    assert re.search(
        r"/test-design --path <[^>]+>|/test-design --path \$\{[^}]+\}", text
    )


def test_documents_unscoped_test_design_invocation_branch(text: str) -> None:
    # Pin the specific branch phrasing rather than any incidental
    # /test-design mention. Prior looser awk allowed lines like line 22's
    # 'come from /test-design (Farley Score + ...)' to satisfy the
    # assertion.
    assert re.search(
        r"unscoped.*dispatch|"
        r"dispatch .*/test-design.*(no scope flag|without --path|no --path)|"
        r"/test-design.*with no scope flag",
        text,
        re.IGNORECASE,
    )


def test_propagates_empty_scope_note(text: str) -> None:
    assert "no in-scope test files" in text


def test_renders_farley_score_scope_label_in_output_block(text: str) -> None:
    # Slice the Output-block section before matching, so an incidental
    # label mention in Step 6 prose alone would not satisfy this
    # assertion.
    lines = text.splitlines()
    collected = []
    on = False
    for line in lines:
        if line.startswith("### Test-design & mutation health"):
            on = True
            collected.append(line)
            continue
        if on and line.startswith("### "):
            on = False
        if on:
            collected.append(line)
    section = "\n".join(collected)
    assert re.search(r"\(all tests\)|\(under [^)]+\)", section)
