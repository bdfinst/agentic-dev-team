"""tests/repo/test_citation_lint_corpus.py must not carry a dead skip-guard
for PR #315 (issue #732).

PR #315 (the citation-lint tool itself) merged long ago, so
`scripts/citation_lint.py` always exists in this repo. A `pytest.skip(...
"not merged")` guard keyed on that PR is permanently dead code that misleads
a reader into thinking the corpus test can legitimately be skipped.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_TEST = REPO_ROOT / "tests" / "repo" / "test_citation_lint_corpus.py"
LINT = REPO_ROOT / "scripts" / "citation_lint.py"


def test_citation_lint_script_exists() -> None:
    # Precondition for the assertion below: the skip-guard's premise (the
    # script might not exist yet) is false and has been false for a long time.
    assert LINT.is_file()


def test_corpus_test_has_no_stale_pr_315_skip_guard() -> None:
    text = CORPUS_TEST.read_text(encoding="utf-8")
    assert "not merged" not in text, (
        f"{CORPUS_TEST} still contains a skip-guard premised on PR #315 not "
        "being merged; remove the dead guard now that citation_lint.py ships."
    )
    assert "pytest.skip" not in text, (
        f"{CORPUS_TEST} should not skip — scripts/citation_lint.py always "
        "exists in this repo."
    )
