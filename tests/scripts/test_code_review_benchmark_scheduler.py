"""Unit tests for the #1000 benchmark harness's budget-aware scheduler.

`scheduler.run_pending()` is exercised entirely through fake `run_case_fn`
callables — no real subprocess, no real `ThreadPoolExecutor` work beyond
what Python itself provides — mirroring the dependency-injection style
`test_code_review_benchmark_runner.py` already uses for `dispatch_fn`.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

import runner
import scheduler


def _noop_kwargs(case: Any) -> dict[str, Any]:
    return {}


def _pending(bug_ids: list[str]):
    """Build `(case, case_dict)` pairs `run_pending()` expects — `case` is
    unused when `make_kwargs` is `_noop_kwargs`, so a bare dict stands in."""
    return [
        (bug_id, {"dataset": "defects4j", "project": "Lang", "bug_id": bug_id})
        for bug_id in bug_ids
    ]


def test_run_pending_prints_progress_and_returns_total(tmp_path: Path) -> None:
    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 1.0}

    total = scheduler.run_pending(
        _pending(["1", "2"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=1,
        run_case_fn=fake_run_case_fn,
    )
    assert total == 2.0
    seen = runner.already_processed(tmp_path)
    assert seen == {"defects4j:Lang:1", "defects4j:Lang:2"}


def test_run_pending_running_total_accumulates_across_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    costs = {"1": 1.00, "2": 2.00, "3": 0.50}

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        return {
            **case_dict,
            "skipped": False,
            "hit": True,
            "cost_usd": costs[case_dict["bug_id"]],
        }

    total = scheduler.run_pending(
        _pending(["1", "2", "3"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=1,  # deterministic completion order
        run_case_fn=fake_run_case_fn,
    )
    assert total == 3.50
    out = capsys.readouterr().out
    assert "($1.00 total)" in out
    assert "($3.00 total)" in out
    assert "($3.50 total)" in out


def test_scheduler_no_max_cost_usd_dispatches_everything(tmp_path: Path) -> None:
    called: list[str] = []

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        called.append(case_dict["bug_id"])
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 5.0}

    scheduler.run_pending(
        _pending(["1", "2", "3"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=2,
        max_cost_usd=None,
        run_case_fn=fake_run_case_fn,
    )
    assert sorted(called) == ["1", "2", "3"]


def test_scheduler_stops_new_dispatch_once_budget_reached(tmp_path: Path) -> None:
    """workers=1: cases complete one at a time, so the budget check after
    case 1 ($5.00 >= $5.00 budget) must stop cases 2 and 3 from ever
    calling run_case_fn — they land in skipped.jsonl instead."""
    called: list[str] = []

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        called.append(case_dict["bug_id"])
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 5.0}

    scheduler.run_pending(
        _pending(["1", "2", "3"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=1,
        max_cost_usd=5.0,
        run_case_fn=fake_run_case_fn,
    )
    assert called == ["1"]

    lines = (tmp_path / "skipped.jsonl").read_text(encoding="utf-8").splitlines()
    skipped_records = [json.loads(line) for line in lines]
    skipped_ids = {r["bug_id"] for r in skipped_records}
    assert skipped_ids == {"2", "3"}
    assert all("--max-cost-usd" in r["reason"] for r in skipped_records)


def test_scheduler_initial_batch_can_exceed_budget_before_first_check(
    tmp_path: Path,
) -> None:
    """workers=3: cases 1, 2, and 3 are all primed before any completion,
    so all three run to completion even though their combined cost ($15)
    exceeds the $5 budget — only case 4 (queued behind them) is skipped."""
    called: list[str] = []

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        called.append(case_dict["bug_id"])
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 5.0}

    scheduler.run_pending(
        _pending(["1", "2", "3", "4"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=3,
        max_cost_usd=5.0,
        run_case_fn=fake_run_case_fn,
    )
    assert sorted(called) == ["1", "2", "3"]

    lines = (tmp_path / "skipped.jsonl").read_text(encoding="utf-8").splitlines()
    skipped_records = [json.loads(line) for line in lines]
    assert {r["bug_id"] for r in skipped_records} == {"4"}


def test_scheduler_in_flight_case_finishes_after_budget_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """workers=2: case A completes immediately and trips the budget; case
    B must already be genuinely blocked (its worker thread has not
    returned) at that moment, and must still be allowed to finish rather
    than being treated as skipped. Deterministic synchronization: B's fake
    run_case_fn blocks on `a_appended` — an Event only set by a wrapped
    `runner.append_result` right after A's real result is appended, which
    happens on the main thread strictly after A's future is drained. B's
    worker thread therefore cannot return before that point, proving B was
    still in flight (not done) at the moment the budget check for A ran."""
    a_appended = threading.Event()

    original_append_result = runner.append_result

    def wrapped_append_result(record, results_dir):
        original_append_result(record, results_dir)
        if record.get("bug_id") == "A":
            a_appended.set()

    monkeypatch.setattr(scheduler.runner, "append_result", wrapped_append_result)

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        if case_dict["bug_id"] == "A":
            return {**case_dict, "skipped": False, "hit": True, "cost_usd": 5.0}
        # Case B: block until A has genuinely been appended by the main
        # thread — guarantees B's future is still un-done at that instant.
        assert a_appended.wait(timeout=5), "A was never appended — test setup broken"
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 0.0}

    scheduler.run_pending(
        [
            ("A", {"dataset": "defects4j", "project": "Lang", "bug_id": "A"}),
            ("B", {"dataset": "defects4j", "project": "Lang", "bug_id": "B"}),
        ],
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=2,
        max_cost_usd=5.0,
        run_case_fn=fake_run_case_fn,
    )

    seen = runner.already_processed(tmp_path)
    # Both A and B completed and were scored (hit) — B was never skipped
    # despite the budget tripping while it was still in flight.
    assert seen == {"defects4j:Lang:A", "defects4j:Lang:B"}

    results_path = tmp_path / "results.jsonl"
    records = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
    ]
    assert {r["bug_id"] for r in records} == {"A", "B"}


def test_scheduler_tops_up_queue_as_futures_complete_when_under_budget(
    tmp_path: Path,
) -> None:
    """workers=2, no budget: submitting case 3 only once one of the first
    two slots frees up proves the top-up mechanism runs (not just the
    stop condition) — all 4 cases must complete."""
    called: list[str] = []

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        called.append(case_dict["bug_id"])
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 1.0}

    total = scheduler.run_pending(
        _pending(["1", "2", "3", "4"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=2,
        run_case_fn=fake_run_case_fn,
    )
    assert sorted(called) == ["1", "2", "3", "4"]
    assert total == 4.0


def test_run_pending_uses_injected_append_fn_not_results_jsonl(tmp_path: Path) -> None:
    """#2051: `append_fn` lets a caller (the recorded-diff dataset) route
    records somewhere other than results.jsonl/skipped.jsonl — proving the
    generalization didn't just add a parameter that's ignored."""
    appended: list[dict[str, Any]] = []

    def fake_append_fn(record: dict[str, Any], results_dir: Any) -> None:
        appended.append(record)

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        return {**case_dict, "dispatched": True, "reason": None, "cost_usd": 0.0}

    scheduler.run_pending(
        _pending(["1"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=1,
        run_case_fn=fake_run_case_fn,
        append_fn=fake_append_fn,
    )

    assert len(appended) == 1
    assert appended[0]["bug_id"] == "1"
    # Never touched the default recall-scoring files.
    assert not (tmp_path / "results.jsonl").is_file()
    assert not (tmp_path / "skipped.jsonl").is_file()


def test_run_pending_default_append_fn_is_monkeypatchable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default `append_fn=None` -> `runner.append_result` resolution must
    stay a live lookup at call time, not a value captured once at import —
    otherwise monkeypatching `runner.append_result` (as existing tests in
    this file do) would silently stop working."""
    seen: list[dict[str, Any]] = []
    original = runner.append_result

    def wrapped(record: dict[str, Any], results_dir: Any) -> None:
        seen.append(record)
        original(record, results_dir)

    monkeypatch.setattr(scheduler.runner, "append_result", wrapped)

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        return {**case_dict, "skipped": False, "hit": True, "cost_usd": 0.0}

    scheduler.run_pending(
        _pending(["1"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=1,
        run_case_fn=fake_run_case_fn,
    )
    assert len(seen) == 1


def test_run_pending_prints_done_for_recorded_diff_record_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A recorded-diff record (`"dispatched"` key, no `hit`/`skipped`) must
    print DONE/FAIL, never HIT/SKIP/MISS — those imply recall scoring that
    never happened for this case type."""

    def fake_run_case_fn(case_dict, **kwargs) -> dict[str, Any]:
        return {**case_dict, "dispatched": True, "reason": None, "cost_usd": 0.0}

    scheduler.run_pending(
        _pending(["1"]),
        make_kwargs=_noop_kwargs,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
        workers=1,
        run_case_fn=fake_run_case_fn,
        append_fn=lambda record, results_dir: None,
    )
    out = capsys.readouterr().out
    assert "DONE" in out
    assert "HIT" not in out
    assert "MISS" not in out
    assert "SKIP" not in out
