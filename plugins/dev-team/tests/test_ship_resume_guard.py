"""ship_resume_guard: every verdict branch, exercised on synthetic state."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ship_resume_guard as g


def pr(n, state, head="x", body="", cross=False):
    return {"number": n, "state": state, "headRefName": head, "body": body,
            "isCrossRepository": cross}


OPEN = {1: "OPEN"}


def test_solo_merged_pr_is_shipped():
    v = g.verdict([1], OPEN, [pr(9, "MERGED", body="Closes #1")], False)
    assert (v["verdict"], v["pr"]) == ("shipped", 9)


def test_solo_closed_issue_is_shipped():
    assert g.verdict([1], {1: "CLOSED"}, [], False)["verdict"] == "shipped"


def test_solo_open_pr_monitors():
    assert g.verdict([1], OPEN, [pr(9, "OPEN", head="issue-1")], False)["verdict"] == "monitor"


def test_passing_mention_is_not_a_signal():
    v = g.verdict([1], OPEN, [pr(9, "OPEN", body="see #1 for context")], False)
    assert v["verdict"] == "first-run"


def test_artifacts_without_pr_resume():
    assert g.verdict([1], OPEN, [], True)["verdict"] == "resume"


def test_nothing_is_first_run():
    assert g.verdict([1], OPEN, [], False)["verdict"] == "first-run"


def test_batch_all_closed_wins_over_unrelated_open_pr():
    st = {1: "CLOSED", 2: "CLOSED"}
    v = g.verdict([1, 2], st, [pr(5, "OPEN", body="Closes #1")], False)
    assert v["verdict"] == "shipped"


def test_batch_mixed_closed_is_partial():
    v = g.verdict([1, 2], {1: "CLOSED", 2: "OPEN"}, [], False)
    assert v["verdict"] == "partial-batch"


def test_batch_mixed_with_own_open_pr_monitors():
    key = g.batch_key([1, 2])
    v = g.verdict([1, 2], {1: "CLOSED", 2: "OPEN"}, [pr(5, "OPEN", head=key)], False)
    assert v["verdict"] == "monitor"


def test_batch_own_pr_monitors():
    key = g.batch_key([2, 1])
    assert key == "issues-1-2"
    v = g.verdict([1, 2], {1: "OPEN", 2: "OPEN"}, [pr(5, "OPEN", head=key)], False)
    assert v["verdict"] == "monitor"


def test_batch_cross_repo_same_branch_is_blocked_not_monitored():
    key = g.batch_key([1, 2])
    fork = pr(5, "OPEN", head=key, body="Closes #1", cross=True)
    v = g.verdict([1, 2], {1: "OPEN", 2: "OPEN"}, [fork], False)
    assert v["verdict"] == "batch-blocked"


def test_batch_foreign_closing_pr_is_blocked():
    v = g.verdict([1, 2], {1: "OPEN", 2: "OPEN"}, [pr(5, "OPEN", body="Fixes #2")], False)
    assert v["verdict"] == "batch-blocked"


def test_parse_issues_rejects_non_numeric():
    with pytest.raises(ValueError):
        g.parse_issues("1,2;rm")
    assert g.parse_issues("3, 4") == [3, 4]
