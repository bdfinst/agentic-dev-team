"""Tests for scripts/epic_auto_close.py (#987).

Covers the pure `should_close_parent` decision function first (Step 1.1);
the CLI wrapper (`get_issue`, `get_sub_issues`, `parent_number_from_url`,
`close_parent`, `main`) is added in Step 1.2 with its own mocked tests.

GitHub's native sub-issues feature tracks completion percentage only; it
does not close a parent/epic issue when every sub-issue closes (verified
directly on epic #971). This test suite locks in the decision logic that
drives the workflow which does perform that close.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import epic_auto_close  # noqa: E402


# ---------------------------------------------------------------------------
# should_close_parent — the pure decision function
# ---------------------------------------------------------------------------


def test_all_sub_issues_closed_returns_true() -> None:
    sub_issues = [{"state": "closed"}, {"state": "closed"}, {"state": "closed"}]
    assert epic_auto_close.should_close_parent(sub_issues) is True


def test_one_sub_issue_still_open_returns_false() -> None:
    sub_issues = [{"state": "closed"}, {"state": "closed"}, {"state": "open"}]
    assert epic_auto_close.should_close_parent(sub_issues) is False


def test_no_sub_issues_returns_false() -> None:
    assert epic_auto_close.should_close_parent([]) is False


def test_mixed_close_reasons_all_closed_returns_true() -> None:
    sub_issues = [
        {"state": "closed", "state_reason": "completed"},
        {"state": "closed", "state_reason": "not_planned"},
    ]
    assert epic_auto_close.should_close_parent(sub_issues) is True


def test_open_sibling_among_mixed_close_reasons_returns_false() -> None:
    sub_issues = [
        {"state": "closed", "state_reason": "completed"},
        {"state": "closed", "state_reason": "not_planned"},
        {"state": "open"},
    ]
    assert epic_auto_close.should_close_parent(sub_issues) is False
