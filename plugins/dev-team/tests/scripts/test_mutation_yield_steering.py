"""Tests for scripts/mutation_yield_steering.py — flag several consecutive
near-zero-yield mutation-kill batches mid-Phase-5 (issue #2033).

The defect these tests pin: Phase 5 had a mid-phase steering check for
coverage (#1790) and none for mutation, so a batch yielding near-zero net
kills did not inform the next batch — the lane ran to the end of the Story
set regardless of what earlier batches showed. This is the more expensive of
the two lanes.

Deliberately mirrors test_coverage_delta_steering.py: #2033 ports #1790's
mechanism rather than inventing one, so the two suites should stay legible
side by side.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
SCRIPT = SCRIPTS_DIR / "mutation_yield_steering.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from mutation_yield_steering import (
    DEFAULT_CONSECUTIVE,
    DEFAULT_MIN_KILLS,
    batch_records,
    evaluate,
    main,
)


def _record(
    batch: str | None,
    starting: object = 10,
    ending: object = 5,
    *,
    before: float = 60.0,
    after: float = 70.0,
    rounds: int = 3,
) -> dict:
    return {
        "phase": 5,
        "captured_at": "2026-08-26T00:00:00Z",
        "batch": batch,
        "module": "payments",
        "starting_survivors": starting,
        "ending_survivors": ending,
        "honest_score_before": before,
        "honest_score_after": after,
        "rounds_spent": rounds,
    }


def _write(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "mutation-history.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


# --- yield measurement ------------------------------------------------------


def test_yield_is_net_survivors_killed():
    result = evaluate([_record("b1", starting=10, ending=4)])
    assert result["batches"][0]["kills"] == 6


def test_a_batch_that_added_survivors_counts_as_flat():
    """Negative yield is not progress — it must not clear the minimum."""
    result = evaluate([_record("b1", starting=4, ending=10)], consecutive=1)
    assert result["batches"][0]["kills"] == -6
    assert result["status"] == "flat_streak"


def test_unmeasurable_yield_breaks_the_streak_rather_than_extending_it():
    """Absence of measurement is not evidence of flatness — the same rule
    #1790 applies to an unmeasurable Story."""
    records = [
        _record("b1", starting=10, ending=10),
        _record("b2", starting=None, ending=None),
        _record("b3", starting=10, ending=10),
    ]
    result = evaluate(records, consecutive=2)
    # b3 is flat, b2 breaks the streak, so the streak is 1 — not 2.
    assert result["streak"] == 1
    assert result["status"] != "flat_streak"


def test_booleans_are_not_accepted_as_survivor_counts():
    """bool is an int subclass in Python but is never a survivor count."""
    result = evaluate([_record("b1", starting=True, ending=False)])
    assert result["batches"][0]["kills"] is None


# --- statuses ---------------------------------------------------------------


def test_flat_streak_at_the_threshold(tmp_path):
    records = [_record("b1", 10, 10), _record("b2", 10, 10)]
    result = evaluate(records, consecutive=2)
    assert result["status"] == "flat_streak"
    assert result["streak"] == 2


def test_flat_streak_forming_is_distinct_from_ok():
    """"Not yet a streak" is not "mutation-kill is producing kills" — the
    false all-clear this gate exists to prevent."""
    # Three measured batches so `insufficient_history` does not outrank the
    # verdict under test, with only the trailing one flat.
    records = [_record("b1", 10, 2), _record("b2", 10, 2), _record("b3", 10, 10)]
    result = evaluate(records, consecutive=3)
    assert result["status"] == "flat_streak_forming"
    assert result["streak"] == 1


def test_insufficient_history_is_not_ok():
    result = evaluate([_record("b1", 10, 2)], consecutive=2)
    assert result["status"] == "insufficient_history"


def test_insufficient_history_when_the_trailing_batch_is_unmeasurable():
    records = [
        _record("b1", 10, 2),
        _record("b2", 10, 2),
        _record("b3", starting=None, ending=None),
    ]
    result = evaluate(records, consecutive=2)
    assert result["status"] == "insufficient_history"


def test_ok_when_the_latest_batch_met_the_minimum():
    records = [_record("b1", 10, 10), _record("b2", 10, 2)]
    result = evaluate(records, consecutive=2)
    assert result["status"] == "ok"


# --- score movement is reported but never decides ---------------------------


def test_score_movement_is_reported():
    result = evaluate([_record("b1", before=60.0, after=72.5)])
    assert result["batches"][0]["score_movement"] == 12.5


def test_score_movement_does_not_rescue_a_flat_yield():
    """A batch can move the percentage without killing survivors on a large
    module; keying the gate on score would make it module-size-dependent."""
    records = [
        _record("b1", 10, 10, before=60.0, after=90.0),
        _record("b2", 10, 10, before=90.0, after=99.0),
    ]
    assert evaluate(records, consecutive=2)["status"] == "flat_streak"


# --- record filtering -------------------------------------------------------


def test_records_without_a_batch_are_excluded():
    """A whole-suite measurement written into the same stream is not a batch
    boundary and must not enter the streak."""
    records = [_record("b1"), _record(None), {"phase": 8, "honest_score_after": 80.0}]
    assert [r["batch"] for r in batch_records(records)] == ["b1"]


# --- CLI contract: exit codes and loud failure ------------------------------


def test_flat_streak_exits_3(tmp_path, capsys):
    history = _write(tmp_path, [_record("b1", 10, 10), _record("b2", 10, 10)])
    assert main(["--history", str(history), "--consecutive", "2"]) == 3


def test_ok_exits_0(tmp_path, capsys):
    history = _write(tmp_path, [_record("b1", 10, 2), _record("b2", 10, 2)])
    assert main(["--history", str(history), "--consecutive", "2"]) == 0


def test_missing_history_exits_2_never_ok(tmp_path, capsys):
    """#1790's trap, ported: an unreadable history must never read as ok."""
    rc = main(["--history", str(tmp_path / "nope.json")])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_non_array_history_exits_2(tmp_path, capsys):
    path = tmp_path / "mutation-history.json"
    path.write_text(json.dumps({"batch": "b1"}), encoding="utf-8")
    assert main(["--history", str(path)]) == 2


def test_corrupt_element_exits_2_rather_than_being_dropped(tmp_path, capsys):
    """A half-rewritten history must not be indistinguishable from a phase
    that simply hasn't closed enough batches yet."""
    path = tmp_path / "mutation-history.json"
    path.write_text(json.dumps([_record("b1"), "garbage"]), encoding="utf-8")
    assert main(["--history", str(path)]) == 2


def test_unparseable_json_exits_2(tmp_path, capsys):
    path = tmp_path / "mutation-history.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["--history", str(path)]) == 2


def test_consecutive_below_one_is_rejected(tmp_path):
    """--consecutive 0 makes the streak check trivially true for any history,
    including an empty one."""
    history = _write(tmp_path, [_record("b1")])
    with __import__("pytest").raises(SystemExit):
        main(["--history", str(history), "--consecutive", "0"])


def test_min_kills_below_one_is_rejected(tmp_path):
    """--min-kills 0 makes every batch — including one that ADDED survivors —
    count as progress."""
    history = _write(tmp_path, [_record("b1")])
    with __import__("pytest").raises(SystemExit):
        main(["--history", str(history), "--min-kills", "0"])


def test_json_output_is_machine_readable(tmp_path, capsys):
    history = _write(tmp_path, [_record("b1", 10, 10), _record("b2", 10, 10)])
    main(["--history", str(history), "--consecutive", "2", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "flat_streak"
    assert payload["streak"] == 2


# --- shared contract with #1790 --------------------------------------------


def test_status_vocabulary_matches_the_coverage_sibling():
    """#2033 ports #1790's mechanism; an operator reading one must already
    know how to read the other, and /test-improve branches on both."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import coverage_delta_steering as coverage
    import mutation_yield_steering as mutation

    assert mutation.STATUS_FLAT == coverage.STATUS_FLAT
    assert mutation.STATUS_FORMING == coverage.STATUS_FORMING
    assert mutation.STATUS_OK == coverage.STATUS_OK
    assert mutation.STATUS_INSUFFICIENT == coverage.STATUS_INSUFFICIENT


def test_runs_as_a_subprocess_under_the_shipped_interpreter(tmp_path):
    """Shipped script: must run standalone, stdlib-only, no import shims."""
    history = _write(tmp_path, [_record("b1", 10, 10), _record("b2", 10, 10)])
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--history", str(history), "--consecutive", "2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3
    assert "flat_streak" in proc.stdout


def test_defaults_are_batch_shaped():
    """mutation-kill runs per batch with --max-rounds 3, so two consecutive
    dead batches is the point at which re-targeting is cheaper than another
    dispatch."""
    assert DEFAULT_MIN_KILLS == 1
    assert DEFAULT_CONSECUTIVE == 2
