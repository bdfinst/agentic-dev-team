"""Tests for scripts/compare_eval_results.py (#2169 Step 2.3).

Covers `compute_fixture_diffs`'s classification (a fixture/agent block with
`issueCount.min > 0` is a defect fixture -- tracks a true-positive-count
proxy; a block with `issueCount.min == 0` is a clean fixture -- tracks a
false-positive-count proxy; a block with no `issueCount`, or a malformed
non-dict `issueCount`, is a third "unclassified" state that is neither), its
regression rule (including the before-present/after-missing "total
detection loss" case), its scope-summary counters, and the CLI's exit-code
contract: a true-positive-count decrease, a false-positive-count increase,
and an after-missing pair all exit non-zero; an unchanged/improved pair
exits zero; a multi-fixture input produces one diff line per fixture/agent
pair.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import compare_eval_results as cer


def _expected_block(stem: str, agent: str, min_count: int) -> dict:
    return {stem: {agent: {"issueCount": {"min": min_count, "max": min_count + 5}}}}


def _actuals_block(stem: str, agent: str, n_issues: int) -> dict:
    return {
        stem: {
            "agents": {
                agent: {
                    "status": "fail" if n_issues else "pass",
                    "issues": [{"severity": "warning", "message": "m"} for _ in range(n_issues)],
                    "summary": "s",
                }
            }
        }
    }


def _merge(*dicts: dict) -> dict:
    out: dict = {}
    for d in dicts:
        for key, value in d.items():
            out.setdefault(key, {}).update(value)
    return out


class TestComputeFixtureDiffsClassification:
    def test_defect_fixture_true_positive_decrease_is_regressed(self):
        expected = _expected_block("fixA", "test-review", 3)
        before = _actuals_block("fixA", "test-review", 4)
        after = _actuals_block("fixA", "test-review", 2)

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert len(rows) == 1
        assert rows[0]["kind"] == "defect"
        assert rows[0]["issuesBefore"] == 4
        assert rows[0]["issuesAfter"] == 2
        assert rows[0]["regressed"] is True
        assert scope == {"compared": 1, "skippedNotComparable": 0, "skippedUnclassified": 0}

    def test_clean_fixture_false_positive_increase_is_regressed(self):
        expected = _expected_block("fixB", "test-review", 0)
        before = _actuals_block("fixB", "test-review", 0)
        after = _actuals_block("fixB", "test-review", 1)

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert len(rows) == 1
        assert rows[0]["kind"] == "clean"
        assert rows[0]["issuesBefore"] == 0
        assert rows[0]["issuesAfter"] == 1
        assert rows[0]["regressed"] is True
        assert scope["compared"] == 1

    def test_unchanged_defect_fixture_is_not_regressed(self):
        expected = _expected_block("fixA", "test-review", 3)
        before = _actuals_block("fixA", "test-review", 4)
        after = _actuals_block("fixA", "test-review", 4)

        rows, _scope = cer.compute_fixture_diffs(before, after, expected)

        assert rows[0]["regressed"] is False

    def test_improved_defect_and_clean_fixtures_are_not_regressed(self):
        expected = _merge(
            _expected_block("fixA", "test-review", 3),
            _expected_block("fixB", "test-review", 0),
        )
        before = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 1),
        )
        after = _merge(
            # true positives increased (fine)
            _actuals_block("fixA", "test-review", 5),
            # false positives decreased (fine)
            _actuals_block("fixB", "test-review", 0),
        )

        rows, _scope = cer.compute_fixture_diffs(before, after, expected)

        assert all(row["regressed"] is False for row in rows)

    def test_before_present_after_missing_is_a_regression(self):
        """Domain-review finding #2: an agent that produced N issues in
        `before` and has NO recorded result at all in `after` (errored,
        timed out) is total detection loss -- the worst-case regression
        this gate exists to catch, not "not comparable"."""
        expected = _expected_block("fixA", "test-review", 3)
        before = _actuals_block("fixA", "test-review", 4)
        after: dict = {}  # no recorded result at all

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert len(rows) == 1
        assert rows[0]["issuesBefore"] == 4
        assert rows[0]["issuesAfter"] is None
        assert rows[0]["regressed"] is True
        assert rows[0]["detail"] == "no result recorded in after"
        assert scope["compared"] == 1
        assert scope["skippedNotComparable"] == 0

    def test_pair_missing_from_before_is_not_comparable(self):
        """Only before-missing is genuinely "new coverage" and skipped --
        the asymmetric half of the fix #2 rule."""
        expected = _expected_block("fixA", "test-review", 3)
        before: dict = {}
        after = _actuals_block("fixA", "test-review", 4)

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert rows == []
        assert scope == {"compared": 0, "skippedNotComparable": 1, "skippedUnclassified": 0}

    def test_missing_issue_count_is_unclassified_not_clean(self):
        """Domain-review finding #3: a block with no `issueCount` must not
        silently default to the "clean" bucket."""
        expected = {"fixA": {"test-review": {}}}
        before = _actuals_block("fixA", "test-review", 0)
        after = _actuals_block("fixA", "test-review", 5)

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert rows == []  # not scored as either "defect" or "clean"
        assert scope == {"compared": 0, "skippedNotComparable": 0, "skippedUnclassified": 1}

    def test_malformed_issue_count_is_treated_as_unclassified(self):
        """Correctness-review finding #4: a non-dict `issueCount` must not
        crash -- treated the same as the "unclassified" case."""
        expected = {"fixA": {"test-review": {"issueCount": 3}}}
        before = _actuals_block("fixA", "test-review", 0)
        after = _actuals_block("fixA", "test-review", 5)

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert rows == []
        assert scope["skippedUnclassified"] == 1

    def test_multi_fixture_input_produces_one_row_per_fixture(self):
        expected = _merge(
            _expected_block("fixA", "test-review", 3),
            _expected_block("fixB", "test-review", 0),
            _expected_block("fixC", "test-review", 2),
        )
        before = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 0),
            _actuals_block("fixC", "test-review", 2),
        )
        after = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 0),
            _actuals_block("fixC", "test-review", 2),
        )

        rows, scope = cer.compute_fixture_diffs(before, after, expected)

        assert len(rows) == 3
        assert {row["fixture"] for row in rows} == {"fixA", "fixB", "fixC"}
        assert scope["compared"] == 3


class TestCli:
    def _write_json(self, path, data) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def _run(self, tmp_path, before: dict, after: dict, expected: dict, check: bool = False):
        expected_dir = tmp_path / "expected"
        expected_dir.mkdir()
        for stem, agents in expected.items():
            self._write_json(
                expected_dir / f"{stem}.json",
                {"fixture": stem, "applicableAgents": list(agents.keys()), "agents": agents},
            )
        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"
        self._write_json(before_path, before)
        self._write_json(after_path, after)
        return subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "compare_eval_results.py"),
                str(before_path),
                str(after_path),
                "--expected-dir",
                str(expected_dir),
            ],
            capture_output=True,
            text=True,
            check=check,
        )

    def test_true_positive_decrease_exits_nonzero(self, tmp_path):
        expected = {"fixA": {"test-review": {"issueCount": {"min": 3, "max": 6}}}}
        before = _actuals_block("fixA", "test-review", 4)
        after = _actuals_block("fixA", "test-review", 2)

        result = self._run(tmp_path, before, after, expected)

        assert result.returncode != 0
        assert "REGRESSION" in result.stdout

    def test_false_positive_increase_exits_nonzero(self, tmp_path):
        expected = {"fixB": {"test-review": {"issueCount": {"min": 0, "max": 1}}}}
        before = _actuals_block("fixB", "test-review", 0)
        after = _actuals_block("fixB", "test-review", 1)

        result = self._run(tmp_path, before, after, expected)

        assert result.returncode != 0
        assert "REGRESSION" in result.stdout

    def test_after_missing_result_exits_nonzero(self, tmp_path):
        expected = {"fixA": {"test-review": {"issueCount": {"min": 3, "max": 6}}}}
        before = _actuals_block("fixA", "test-review", 4)
        after: dict = {}

        result = self._run(tmp_path, before, after, expected)

        assert result.returncode != 0
        assert "REGRESSION" in result.stdout
        assert "no result recorded in after" in result.stdout

    def test_unchanged_or_improved_pair_exits_zero(self, tmp_path):
        expected = {
            "fixA": {"test-review": {"issueCount": {"min": 3, "max": 6}}},
            "fixB": {"test-review": {"issueCount": {"min": 0, "max": 1}}},
        }
        before = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 1),
        )
        after = _merge(
            _actuals_block("fixA", "test-review", 5),
            _actuals_block("fixB", "test-review", 0),
        )

        result = self._run(tmp_path, before, after, expected, check=True)

        assert result.returncode == 0
        assert "No regressions" in result.stdout

    def test_multi_fixture_input_produces_one_diff_line_per_fixture(self, tmp_path):
        expected = {
            "fixA": {"test-review": {"issueCount": {"min": 3, "max": 6}}},
            "fixB": {"test-review": {"issueCount": {"min": 0, "max": 1}}},
            "fixC": {"test-review": {"issueCount": {"min": 2, "max": 4}}},
        }
        before = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 0),
            _actuals_block("fixC", "test-review", 2),
        )
        after = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 0),
            _actuals_block("fixC", "test-review", 2),
        )

        result = self._run(tmp_path, before, after, expected, check=True)

        diff_lines = [line for line in result.stdout.splitlines() if "::test-review" in line]
        assert len(diff_lines) == 3

    def test_scope_summary_line_reports_compared_and_skipped_counts(self, tmp_path):
        """Domain-review finding #6: "No regressions." must not print
        without also surfacing how much was actually compared vs. skipped."""
        expected = {
            "fixA": {"test-review": {"issueCount": {"min": 3, "max": 6}}},
            "fixB": {"test-review": {}},  # unclassified: no issueCount
        }
        before = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 0),
        )
        after = _merge(
            _actuals_block("fixA", "test-review", 3),
            _actuals_block("fixB", "test-review", 0),
        )

        result = self._run(tmp_path, before, after, expected, check=True)

        assert "compared 1 pair(s); skipped 1 (0 not-in-both-runs, 1 unclassified/malformed)" in result.stdout

    def test_missing_before_file_exits_usage_error(self, tmp_path):
        expected = {"fixA": {"test-review": {"issueCount": {"min": 3, "max": 6}}}}
        expected_dir = tmp_path / "expected"
        expected_dir.mkdir()
        self._write_json(
            expected_dir / "fixA.json",
            {"fixture": "fixA", "applicableAgents": ["test-review"], "agents": expected["fixA"]},
        )
        after_path = tmp_path / "after.json"
        self._write_json(after_path, _actuals_block("fixA", "test-review", 3))

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "compare_eval_results.py"),
                str(tmp_path / "does-not-exist.json"),
                str(after_path),
                "--expected-dir",
                str(expected_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 2
        assert "cannot read" in result.stderr.lower()
