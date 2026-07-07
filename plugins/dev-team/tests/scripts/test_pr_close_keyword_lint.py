"""Unit tests for scripts/pr_close_keyword_lint.py (issue #977).

Covers the two accidental-auto-close shapes: a closing keyword negated in
the same sentence, and a closing keyword match that contradicts a
`Part of #N` reference elsewhere in the body.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import pr_close_keyword_lint as lint  # noqa: E402


def test_negated_closing_keyword_is_flagged():
    """The exact #975 shape: "does not close #967" still matches GitHub's
    dumb regex and must be flagged even though the sentence negates it."""
    body = "This PR does not close #967, only part of it is fixed."
    findings = lint.find_findings(body)
    assert len(findings) == 1
    assert findings[0].issue == 967
    assert findings[0].type == "negated-closing-keyword"


def test_clean_closes_and_part_of_is_not_flagged():
    body = "Closes #123.\nPart of #200."
    assert lint.find_findings(body) == []


def test_closing_keyword_conflicting_with_part_of_is_flagged():
    body = "Closes #123 and Part of #123 both listed."
    findings = lint.find_findings(body)
    assert len(findings) == 1
    assert findings[0].issue == 123
    assert findings[0].type == "conflicts-with-part-of"


def test_wont_fix_phrasing_is_flagged():
    body = "This change won't fix #55 — that's tracked separately."
    findings = lint.find_findings(body)
    assert len(findings) == 1
    assert findings[0].issue == 55


def test_negation_in_prior_sentence_does_not_leak_across_boundary():
    """A negation word in an earlier, unrelated sentence must not suppress
    a genuine, intentional closing reference in a later sentence."""
    body = "This does not touch auth. Closes #10."
    assert lint.find_findings(body) == []


def test_multiple_issues_only_flags_the_problematic_one():
    body = "Closes #10. This does not close #20, deferred to a follow-up."
    findings = lint.find_findings(body)
    assert len(findings) == 1
    assert findings[0].issue == 20
