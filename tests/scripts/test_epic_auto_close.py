"""Tests for scripts/epic_auto_close.py (#987).

Covers the pure `should_close_parent` decision function, `parent_number_from_url`,
and the CLI wrapper (`get_issue`, `get_sub_issues`, `close_parent`, `main`) —
all mocked at the `subprocess.run` boundary, no real `gh`/network call. See
epic_auto_close.py's module docstring for why this script exists.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import epic_auto_close

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


# ---------------------------------------------------------------------------
# parent_number_from_url
# ---------------------------------------------------------------------------


def test_parent_number_from_url_normal() -> None:
    url = "https://api.github.com/repos/OWNER/REPO/issues/971"
    assert epic_auto_close.parent_number_from_url(url) == 971


def test_parent_number_from_url_trailing_slash() -> None:
    url = "https://api.github.com/repos/OWNER/REPO/issues/971/"
    assert epic_auto_close.parent_number_from_url(url) == 971


def test_parent_number_from_url_single_digit() -> None:
    url = "https://api.github.com/repos/OWNER/REPO/issues/5"
    assert epic_auto_close.parent_number_from_url(url) == 5


# ---------------------------------------------------------------------------
# CLI — main(), fully mocked at the subprocess boundary (no real gh/network call)
# ---------------------------------------------------------------------------


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout=stdout, stderr=""
    )


def test_cli_no_ops_when_no_parent() -> None:
    child_issue = _completed('{"number": 42, "state": "closed"}')
    with patch("epic_auto_close.subprocess.run", return_value=child_issue) as mock_run:
        rc = epic_auto_close.main(["--repo", "OWNER/REPO", "--issue", "42"])
    assert rc == 0
    # Only the single get_issue call for the closed issue itself — no close call.
    assert mock_run.call_count == 1


def test_cli_no_ops_when_parent_already_closed() -> None:
    child_issue = _completed(
        '{"number": 42, "state": "closed", '
        '"parent_issue_url": "https://api.github.com/repos/OWNER/REPO/issues/971"}'
    )
    parent_issue = _completed('{"number": 971, "state": "closed"}')
    with patch(
        "epic_auto_close.subprocess.run", side_effect=[child_issue, parent_issue]
    ) as mock_run:
        rc = epic_auto_close.main(["--repo", "OWNER/REPO", "--issue", "42"])
    assert rc == 0
    assert mock_run.call_count == 2


def test_cli_closes_parent_when_all_sub_issues_closed() -> None:
    child_issue = _completed(
        '{"number": 42, "state": "closed", '
        '"parent_issue_url": "https://api.github.com/repos/OWNER/REPO/issues/971"}'
    )
    parent_issue = _completed('{"number": 971, "state": "open"}')
    sub_issues = _completed('[{"state": "closed"}, {"state": "closed"}]')
    close_result = _completed("")
    with patch(
        "epic_auto_close.subprocess.run",
        side_effect=[child_issue, parent_issue, sub_issues, close_result],
    ) as mock_run:
        rc = epic_auto_close.main(["--repo", "OWNER/REPO", "--issue", "42"])
    assert rc == 0
    assert mock_run.call_count == 4

    close_call_args = mock_run.call_args_list[-1].args[0]
    assert close_call_args[:3] == ["gh", "issue", "close"]
    assert "971" in close_call_args

    comment_index = close_call_args.index("--comment") + 1
    comment_text = close_call_args[comment_index]
    assert "epic-auto-close" in comment_text
    assert "#42" in comment_text


def test_cli_does_not_close_when_gh_api_fails() -> None:
    with patch(
        "epic_auto_close.subprocess.run",
        side_effect=subprocess.CalledProcessError(
            1, ["gh", "api", "repos/OWNER/REPO/issues/42"]
        ),
    ) as mock_run, pytest.raises(subprocess.CalledProcessError):
        epic_auto_close.main(["--repo", "OWNER/REPO", "--issue", "42"])
    # Only the failing get_issue call happened — never reached close_parent.
    assert mock_run.call_count == 1
