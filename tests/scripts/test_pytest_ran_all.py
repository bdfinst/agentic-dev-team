"""Tests for scripts/pytest_ran_all.py — did a pytest run pass something and skip nothing."""

from __future__ import annotations

import pytest

from scripts import pytest_ran_all


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("........\n97 passed in 11.90s\n", True),
        ("=========== 12 passed, 1 warning in 0.5s ===========\n", True),
        ("97 passed, 3 skipped in 11.90s\n", False),
        ("=== 1 failed, 4 passed, 2 skipped in 1.0s ===\n", False),
        ("1 skipped in 0.01s\n", False),
        ("no tests ran in 0.01s\n", False),
        ("", False),
        ("collected 0 items\n", False),
        ("SKIPPED [1] a.py:3: reason\n97 passed in 1.0s\n", True),
        ("97 passed in 1.0s\nthen noise 3 skipped\n", True),
        ("5 passed in 1.0s (0:00:01)\n", True),
        ("5 passed, 1 skipped in 1.0s (0:00:01)\n", False),
    ],
)
def test_a_run_counts_only_when_it_passed_something_and_skipped_nothing(
    output, expected
):
    assert pytest_ran_all.ran_all(output) is expected


def test_the_last_summary_line_decides():
    assert pytest_ran_all.summary_counts(
        "2 passed in 1s\n3 passed, 1 skipped in 2s\n"
    ) == {
        "passed": 3,
        "skipped": 1,
    }


def test_main_reads_the_file_and_maps_the_verdict_to_the_exit_code(tmp_path):
    ok, skipped = tmp_path / "ok.txt", tmp_path / "skipped.txt"
    ok.write_text("3 passed in 0.1s\n", encoding="utf-8")
    skipped.write_text("3 passed, 1 skipped in 0.1s\n", encoding="utf-8")
    assert pytest_ran_all.main([str(ok)]) == 0
    assert pytest_ran_all.main([str(skipped)]) == 1
    assert pytest_ran_all.main([str(tmp_path / "absent.txt")]) == 1
    assert pytest_ran_all.main([]) == 1
