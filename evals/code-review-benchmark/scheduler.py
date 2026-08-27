"""Bounded, budget-aware case scheduler for the /code-review benchmark
harness (#1000).

Runs a list of pending cases through a `ThreadPoolExecutor`, submitting at
most `workers` cases at a time and topping up as each completes — rather
than submitting every case upfront and draining via `as_completed()` (the
harness's original shape, still visible in git history). That "submit all,
then drain" shape cannot give `--max-cost-usd` a real "stop new dispatch"
guarantee: `Future.cancel()` only succeeds for futures the pool hasn't
started yet, a race that can't be tested deterministically. This module
makes "no case is submitted after the cutoff" an actual invariant instead:
a case is only ever handed to the executor from this module's own
`submit_one()` closure, so once submission stops, it stays stopped.

`concurrent.futures.as_completed()` is deliberately NOT used here — it
snapshots its input set at call time and cannot accept futures added after
iteration starts. Instead this loops on `concurrent.futures.wait(in_flight,
return_when=FIRST_COMPLETED)`, rebuilding the `in_flight` set each pass.

Extracted out of `cli.py` (rather than grown inside it) because `cli.py`
already carries argparse wiring, dataset/adapter selection, and bootstrap
— a fourth responsibility (cost accounting + budget scheduling) belongs in
its own single-purpose module. `run_pending()` has no adapter/dataset
knowledge of its own (see `make_kwargs`), mirroring `cli.py`'s existing
`_make_checkout_fn`/`_make_test_fn` factory pattern.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import runner

CaseAndDict = tuple[Any, dict[str, Any]]


def run_pending(
    pending: list[CaseAndDict],
    make_kwargs: Callable[[Any], dict[str, Any]],
    dispatch_fn: Callable[[str, str], dict[str, Any]],
    results_dir: Any,
    workers: int,
    max_cost_usd: float | None = None,
    run_case_fn: Callable[..., dict[str, Any]] = runner.run_case,
    append_fn: Callable[[dict[str, Any], Any], None] | None = None,
) -> float:
    """Run every `(case, case_dict)` pair in `pending` to completion.

    Submits up to `workers` cases before the first completion — so
    `max_cost_usd` is checked only *after* a completion, never before that
    initial batch, meaning realized spend can exceed it by up to
    `workers - 1` extra in-flight cases' cost (disclosed, not a bug — see
    the plan's Decisions & Assumptions). Once the running total meets or
    exceeds `max_cost_usd`, no further case is submitted; already
    in-flight futures are never cancelled and always finish normally.
    Cases still queued when the cutoff engages are recorded via `append_fn`
    as skip records (never silently dropped) and a single, clear message is
    printed to stderr explaining why.

    `make_kwargs(case) -> dict` supplies the per-case `run_case_fn` keyword
    arguments (checkout_fn/ground_truth_fn/test_fn/scope/tolerance) — this
    function itself has no adapter/dataset knowledge.

    `run_case_fn`/`append_fn` (#2051) default to the Defects4J/BugsJS recall
    pair (`runner.run_case`/`runner.append_result`, writing
    `results.jsonl`/`skipped.jsonl`). The recorded-diff adapter passes
    `runner.run_recorded_diff_case`/`runner.append_recorded_diff_result`
    instead — that case type has no `hit`/`skipped` recall semantics, and
    `report.py`'s recall math must never see one of its records.

    Returns the final running cost total (USD).
    """
    # Resolved here, not as a parameter default — a parameter default binds
    # `runner.append_result` once at import time, which would make it
    # immune to test/runtime monkeypatching of `runner.append_result`
    # itself (existing tests patch the module attribute, not this
    # function's signature).
    if append_fn is None:
        append_fn = runner.append_result
    results_dir = Path(results_dir)
    queue: list[CaseAndDict] = list(pending)
    total = len(queue)
    processed = 0
    running_total = 0.0
    budget_stopped = False
    workers = max(1, workers)

    def _print_progress(record: dict[str, Any], key: str) -> None:
        nonlocal processed
        processed += 1
        if "dispatched" in record:
            # Recorded-diff record shape — no hit/skipped recall semantics.
            status = "DONE" if record.get("dispatched") and not record.get(
                "reason"
            ) else "FAIL"
        else:
            status = (
                "HIT"
                if record.get("hit")
                else ("SKIP" if record.get("skipped") else "MISS")
            )
        print(f"[{processed}/{total}] {key}: {status} (${running_total:.2f} total)")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        in_flight: dict[Future, dict[str, Any]] = {}

        def submit_one() -> None:
            case, case_dict = queue.pop(0)
            future = executor.submit(
                run_case_fn,
                case_dict,
                dispatch_fn=dispatch_fn,
                results_dir=results_dir,
                **make_kwargs(case),
            )
            in_flight[future] = case_dict

        while queue and len(in_flight) < workers:
            submit_one()

        while in_flight:
            done, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
            for future in done:
                case_dict = in_flight.pop(future)
                key = runner.case_key(case_dict)
                try:
                    record = future.result()
                except Exception as exc:  # noqa: BLE001 - one case's crash must not abort the batch
                    record = runner.skip_record(case_dict, f"internal error: {exc}")

                append_fn(record, results_dir)
                running_total += record.get("cost_usd") or 0.0
                _print_progress(record, key)

                if (
                    not budget_stopped
                    and max_cost_usd is not None
                    and running_total >= max_cost_usd
                    and queue
                ):
                    budget_stopped = True
                    print(
                        f"code-review-benchmark: --max-cost-usd {max_cost_usd} "
                        f"reached (running total ${running_total:.2f}) — stopping "
                        f"new dispatch; {len(queue)} not-yet-started case(s) will "
                        "be recorded as skipped. Cases already in flight will "
                        "still finish.",
                        file=sys.stderr,
                    )

                if queue and not budget_stopped:
                    submit_one()

        # Only reached when the budget cutoff tripped while cases were
        # still queued — record each as an explicit, visible skip rather
        # than silently dropping it.
        while queue:
            _, case_dict = queue.pop(0)
            record = runner.skip_record(
                case_dict,
                f"--max-cost-usd {max_cost_usd} reached before dispatch "
                f"(running total ${running_total:.2f})",
                cost_usd=None,
            )
            append_fn(record, results_dir)
            _print_progress(record, runner.case_key(case_dict))

    return running_total


if __name__ == "__main__":
    sys.stderr.write("scheduler.py is a library — invoke via cli.py\n")
    raise SystemExit(1)
