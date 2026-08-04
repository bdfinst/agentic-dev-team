"""Tests for scripts/coverage_delta_steering.py — flag several consecutive
near-zero-coverage-delta Stories mid-Phase-5 (issue #1790).

The defect these tests pin: per-Story coverage deltas were only reviewed at
the end of a run, so a Phase 5 could keep closing Stories and reporting
mutation-kill progress while line coverage stayed flat — the phase's whole
budget spent on the wrong layer before anyone noticed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
SCRIPT = SCRIPTS_DIR / "coverage_delta_steering.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_delta_steering import (
    DEFAULT_CONSECUTIVE,
    DEFAULT_MIN_LINE_DELTA,
    evaluate,
    main,
    story_snapshots,
)


def _snapshot(story: str | None, line_pct: float, branch_pct: float | None = None) -> dict:
    return {
        "phase": 5,
        "captured_at": "2026-08-04T00:00:00Z",
        "story": story,
        "line_pct": line_pct,
        "branch_pct": branch_pct,
        "baseline_line_pct": 70.0,
        "baseline_branch_pct": 50.0,
    }


def _history(tmp_path: Path, snapshots: list[dict]) -> Path:
    path = tmp_path / "coverage-history.json"
    path.write_text(json.dumps(snapshots), encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _json_run(*args: str) -> tuple[int, dict]:
    proc = _run(*args, "--json")
    return proc.returncode, json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# snapshot selection
# ---------------------------------------------------------------------------


def test_story_snapshots_keeps_only_story_attributed_entries():
    history = [
        _snapshot(None, 70.0),
        _snapshot("S-1", 70.1),
        _snapshot("", 70.2),
        _snapshot("S-2", 70.3),
    ]
    assert [s["story"] for s in story_snapshots(history)] == ["S-1", "S-2"]


def test_first_story_movement_is_measured_against_the_baseline():
    result = evaluate([_snapshot("S-1", 72.0)])
    assert result["stories"][0]["line_movement"] == 2.0


def test_later_story_movement_is_measured_against_the_previous_story():
    result = evaluate([_snapshot("S-1", 72.0), _snapshot("S-2", 72.5)])
    assert result["stories"][1]["line_movement"] == 0.5


def test_movement_falls_back_to_the_previous_snapshot_when_no_baseline_is_recorded():
    first = _snapshot("S-1", 72.0)
    del first["baseline_line_pct"]
    result = evaluate([first, _snapshot("S-2", 72.4)])
    assert result["stories"][0]["line_movement"] is None
    assert result["stories"][1]["line_movement"] == 0.4


# ---------------------------------------------------------------------------
# streak detection — the #1790 core behavior
# ---------------------------------------------------------------------------


def test_three_consecutive_flat_stories_are_flagged():
    result = evaluate(
        [
            _snapshot("S-1", 70.0),
            _snapshot("S-2", 70.0),
            _snapshot("S-3", 70.01),
        ]
    )
    assert result["status"] == "flat_streak"
    assert result["streak"] == 3
    assert [s["story"] for s in result["flat_stories"]] == ["S-1", "S-2", "S-3"]


def test_two_flat_stories_are_not_yet_a_streak():
    result = evaluate([_snapshot("S-1", 70.0), _snapshot("S-2", 70.0)])
    assert result["status"] == "insufficient_history"
    assert result["streak"] == 2


def test_a_real_move_resets_the_streak():
    result = evaluate(
        [
            _snapshot("S-1", 70.0),
            _snapshot("S-2", 70.0),
            _snapshot("S-3", 78.0),
        ]
    )
    assert result["status"] == "ok"
    assert result["streak"] == 0


def test_only_the_trailing_stories_count_toward_the_streak():
    """A flat run earlier in the phase that has since recovered must not
    keep re-firing the prompt."""
    result = evaluate(
        [
            _snapshot("S-1", 70.0),
            _snapshot("S-2", 70.0),
            _snapshot("S-3", 70.0),
            _snapshot("S-4", 80.0),
        ]
    )
    assert result["status"] == "ok"


def test_story_counts_are_reported():
    result = evaluate([_snapshot("S-1", 70.0), _snapshot("S-2", 70.0)])
    assert result["stories_evaluated"] == 2
    assert result["stories_measured"] == 2


def test_a_negative_delta_counts_as_flat_not_as_progress():
    result = evaluate(
        [
            _snapshot("S-1", 70.0),
            _snapshot("S-2", 69.5),
            _snapshot("S-3", 69.4),
        ]
    )
    assert result["status"] == "flat_streak"
    assert result["flat_stories"][1]["line_movement"] == -0.5


def test_stories_with_unmeasurable_movement_break_the_streak_rather_than_extend_it():
    """A snapshot with no comparable predecessor is not evidence of flatness."""
    first = _snapshot("S-1", 74.0)
    del first["baseline_line_pct"]
    result = evaluate([first, _snapshot("S-2", 74.0), _snapshot("S-3", 74.0)])
    assert result["status"] == "insufficient_history"
    assert result["streak"] == 2


def test_a_short_streak_is_not_reported_as_ok():
    """correctness-review: with enough measured Stories but a below-minimum
    trailing Story, `ok` would have claimed "targeting is producing coverage
    movement" about a Story that moved +0.0 — the exact false all-clear #1790
    exists to prevent."""
    result = evaluate(
        [_snapshot("S-1", 80.0), _snapshot("S-2", 90.0), _snapshot("S-3", 90.0)]
    )
    assert result["status"] == "flat_streak_forming"
    assert result["streak"] == 1


def test_flat_streak_forming_exits_0_but_names_the_streak(tmp_path):
    history = _history(
        tmp_path,
        [_snapshot("S-1", 80.0), _snapshot("S-2", 90.0), _snapshot("S-3", 90.0)],
    )
    code, payload = _json_run("--history", str(history))
    assert code == 0
    assert payload["status"] == "flat_streak_forming"
    assert "1 of 3" in payload["message"]


def test_an_unmeasurable_trailing_story_does_not_crash_the_ok_branch():
    """correctness-review: formatting a None movement raised TypeError, so a
    trailing snapshot with no line_pct crashed the gate instead of reporting
    a verdict."""
    last = _snapshot("S-4", 90.0)
    last["line_pct"] = None
    result = evaluate(
        [
            _snapshot("S-1", 80.0),
            _snapshot("S-2", 90.0),
            _snapshot("S-3", 95.0),
            last,
        ]
    )
    assert result["status"] == "insufficient_history"
    assert "could not be measured" in result["message"]


def test_movement_exactly_at_the_threshold_is_not_flat():
    result = evaluate(
        [_snapshot("S-1", 70.1), _snapshot("S-2", 70.2), _snapshot("S-3", 70.3)],
        min_line_delta=0.1,
    )
    assert result["status"] == "ok"
    assert result["streak"] == 0


def test_movement_is_not_rounded_up_across_the_threshold():
    """A true movement of 0.096 must stay below a 0.1 minimum — rounding for
    display must not decide the gate."""
    result = evaluate(
        [
            _snapshot("S-1", 70.096),
            _snapshot("S-2", 70.192),
            _snapshot("S-3", 70.288),
        ],
        min_line_delta=0.1,
    )
    assert result["status"] == "flat_streak"


def test_thresholds_are_tunable():
    snapshots = [_snapshot("S-1", 70.0), _snapshot("S-2", 70.2), _snapshot("S-3", 70.4)]
    assert evaluate(snapshots, min_line_delta=0.1)["status"] == "ok"
    assert evaluate(snapshots, min_line_delta=1.0)["status"] == "flat_streak"
    assert evaluate(snapshots, min_line_delta=1.0, consecutive=4)["status"] == (
        "insufficient_history"
    )


def test_running_average_line_movement_is_reported():
    result = evaluate([_snapshot("S-1", 71.0), _snapshot("S-2", 73.0)])
    assert result["running_average_line_movement"] == 1.5


def test_branch_movement_is_reported_but_does_not_drive_the_verdict():
    """Branch coverage is not natively available on every stack (Go), so the
    streak decision keys off line movement only."""
    result = evaluate(
        [
            _snapshot("S-1", 70.0, branch_pct=51.0),
            _snapshot("S-2", 70.0, branch_pct=60.0),
            _snapshot("S-3", 70.0, branch_pct=70.0),
        ]
    )
    assert result["status"] == "flat_streak"
    assert result["stories"][2]["branch_movement"] == 10.0


def test_empty_history_is_insufficient_not_flat():
    result = evaluate([])
    assert result["status"] == "insufficient_history"
    assert result["stories"] == []


def test_evaluate_records_the_thresholds_it_used():
    result = evaluate([_snapshot("S-1", 71.0)])
    assert result["min_line_delta"] == DEFAULT_MIN_LINE_DELTA
    assert result["consecutive_threshold"] == DEFAULT_CONSECUTIVE


def test_flat_streak_message_points_back_at_phase_1_targeting():
    result = evaluate(
        [_snapshot("S-1", 70.0), _snapshot("S-2", 70.0), _snapshot("S-3", 70.0)]
    )
    assert "targeting" in result["message"].lower()


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_cli_exit_3_on_a_flat_streak(tmp_path):
    history = _history(
        tmp_path,
        [_snapshot("S-1", 70.0), _snapshot("S-2", 70.0), _snapshot("S-3", 70.0)],
    )
    code, payload = _json_run("--history", str(history))
    assert code == 3
    assert payload["status"] == "flat_streak"


def test_cli_exit_0_when_coverage_is_moving(tmp_path):
    history = _history(
        tmp_path,
        [_snapshot("S-1", 71.0), _snapshot("S-2", 74.0), _snapshot("S-3", 78.0)],
    )
    code, payload = _json_run("--history", str(history))
    assert code == 0
    assert payload["status"] == "ok"


def test_cli_exit_0_on_insufficient_history(tmp_path):
    history = _history(tmp_path, [_snapshot("S-1", 71.0)])
    code, payload = _json_run("--history", str(history))
    assert code == 0
    assert payload["status"] == "insufficient_history"


def test_cli_missing_history_exits_2(tmp_path):
    proc = _run("--history", str(tmp_path / "absent.json"), "--json")
    assert proc.returncode == 2
    assert "not found" in (proc.stdout + proc.stderr).lower()


def test_cli_malformed_history_exits_2(tmp_path):
    path = tmp_path / "coverage-history.json"
    path.write_text("{not json", encoding="utf-8")
    proc = _run("--history", str(path), "--json")
    assert proc.returncode == 2


def test_cli_history_that_is_not_a_list_exits_2(tmp_path):
    path = tmp_path / "coverage-history.json"
    path.write_text(json.dumps({"story": "S-1"}), encoding="utf-8")
    proc = _run("--history", str(path), "--json")
    assert proc.returncode == 2


def test_cli_history_with_a_non_dict_entry_exits_2(tmp_path):
    """correctness-review: silently dropping non-dict entries made a corrupt
    or half-rewritten history indistinguishable from a phase that has not run
    enough Stories yet — a clean result from unusable evidence."""
    path = tmp_path / "coverage-history.json"
    path.write_text(json.dumps([_snapshot("S-1", 71.0), "S-2"]), encoding="utf-8")
    proc = _run("--history", str(path), "--json")
    assert proc.returncode == 2
    assert "index 1" in (proc.stdout + proc.stderr)


def test_cli_rejects_a_consecutive_threshold_below_one(tmp_path):
    """`--consecutive 0` made `len(streak) >= consecutive` trivially true, so
    any history — including an empty one — reported a flat streak."""
    history = _history(tmp_path, [])
    proc = _run("--history", str(history), "--consecutive", "0")
    assert proc.returncode == 2
    assert "--consecutive" in (proc.stdout + proc.stderr)


def test_cli_rejects_a_negative_min_line_delta(tmp_path):
    history = _history(tmp_path, [])
    proc = _run("--history", str(history), "--min-line-delta", "-1")
    assert proc.returncode == 2
    assert "--min-line-delta" in (proc.stdout + proc.stderr)


def test_cli_text_output_lists_the_flat_stories(tmp_path):
    history = _history(
        tmp_path,
        [_snapshot("S-1", 70.0), _snapshot("S-2", 70.0), _snapshot("S-3", 70.0)],
    )
    proc = _run("--history", str(history))
    assert proc.returncode == 3
    assert "S-2" in proc.stdout
    assert "flat_streak" in proc.stdout


def test_cli_threshold_flags_are_wired(tmp_path):
    history = _history(
        tmp_path,
        [_snapshot("S-1", 70.0), _snapshot("S-2", 70.2), _snapshot("S-3", 70.4)],
    )
    assert main(["--history", str(history), "--json"]) == 0
    assert main(["--history", str(history), "--min-line-delta", "1.0", "--json"]) == 3
    assert (
        main(
            [
                "--history",
                str(history),
                "--min-line-delta",
                "1.0",
                "--consecutive",
                "4",
                "--json",
            ]
        )
        == 0
    )
