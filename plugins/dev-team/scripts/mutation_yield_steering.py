#!/usr/bin/env python3
"""mutation_yield_steering.py — turn per-batch mutation yield into a live
Phase-5 steering signal (issue #2033).

Why this exists. Phase 5 has a mid-phase steering check for coverage (#1790,
``coverage_delta_steering.py``) and none for mutation. `mutation-kill` is
dispatched once per module batch (#1963) with ``--max-rounds 3``, and a batch
that yields near-zero net kills does not inform the next batch — the lane runs
to the end of the Story set regardless of what the earlier batches showed.
That is exactly the failure #1790 was written to stop, in the more expensive of
the two lanes: `mutation-kill` is 34.4% of thread messages in the 11-25 Aug
2026 corpus against 5.1% for every review lens combined.

This is a **port of #1790's mechanism, not a new one**. It shares that
script's status vocabulary and exit-code contract deliberately, so an operator
reading one already knows how to read the other, and so `/test-improve` can
branch on both identically.

The unit is the **batch**, not the Story. `mutation-kill` now runs per batch,
so a per-Story mutation check would have no observation to make on most
Stories — the signal only exists at a batch boundary.

Yield, per batch, is ``starting_survivors - ending_survivors``: the net
survivors killed. A **negative** yield counts as flat — a batch that ended
with more survivors than it started is certainly not progress. A batch whose
yield cannot be measured (either count missing or non-numeric) has yield
``None`` and **breaks** the streak rather than extending it: absence of
measurement is not evidence of flatness.

Honest score before/after is reported alongside but does **not** drive the
verdict. Score movement depends on the size of the file's mutant set, so a
batch over a large module can kill real survivors while barely moving the
percentage; keying the gate on it would make the check silently
module-size-dependent. This mirrors #1790's reason for not keying on branch
coverage.

Statuses (and exit codes):

- ``flat_streak`` (3) — ``--consecutive`` or more trailing batches each yielded
  fewer than ``--min-kills``. The caller prompts; this script does not decide
  policy.
- ``flat_streak_forming`` (0) — the trailing batch yielded less than the
  minimum but the streak is still shorter than ``--consecutive``. A distinct
  status rather than ``ok``, because "not yet a streak" is not "mutation-kill
  is producing kills".
- ``insufficient_history`` (0) — fewer measurable batches than
  ``--consecutive``, or a trailing batch whose yield could not be measured at
  all, so no streak verdict is possible yet.
- ``ok`` (0) — the trailing batch yielded at least the minimum.
- exit ``2`` — the history file is missing, unreadable, not JSON, not a JSON
  array, or carries a non-record element; also an out-of-range
  ``--consecutive``/``--min-kills``. **Never** reported as an all-clear — the
  same trap #1790 calls out.

Stdlib-only (ADR 0014/0015), Python 3.10+ floor (ADR 0031).

Usage:
    python3 mutation_yield_steering.py \\
      --history .dev-team-reports/test-improve/<slug>/data/mutation-history.json
    python3 mutation_yield_steering.py --history <path> \\
      --min-kills 1 --consecutive 2 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MIN_KILLS = 1
DEFAULT_CONSECUTIVE = 2

STATUS_FLAT = "flat_streak"
STATUS_FORMING = "flat_streak_forming"
STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_history"

# Score movements are rounded only to kill binary-float artifacts
# (72.4 - 72.0 = 0.40000000000000568). Yield itself is an integer count and is
# never rounded. Score never decides the verdict — see the module docstring.
_SCORE_PRECISION = 10


class HistoryError(ValueError):
    """The mutation history could not be read or is not a record array."""


def load_history(path: Path) -> list[dict]:
    """Read ``mutation-history.json``, raising HistoryError on anything that is
    not a readable JSON array of batch-record objects."""
    if not path.is_file():
        raise HistoryError(f"mutation history not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryError(f"{path}: unreadable mutation history ({exc})") from exc
    if not isinstance(payload, list):
        raise HistoryError(
            f"{path}: mutation history must be a JSON array of batch records, "
            f"got {type(payload).__name__}"
        )
    # A non-dict element means the file is corrupt or half-rewritten. Dropping
    # it silently would leave a corrupt history indistinguishable from a phase
    # that simply hasn't closed enough batches yet — a clean verdict from
    # unusable evidence, which is the one thing this gate must never produce.
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise HistoryError(
                f"{path}: mutation history entry at index {index} is a "
                f"{type(entry).__name__}, not a batch record"
            )
    return list(payload)


def batch_records(history: list[dict]) -> list[dict]:
    """Keep only batch-attributed records — the per-batch Phase-5 dispatches.

    A record with no ``batch`` is not a batch boundary (e.g. a whole-suite
    Phase-8 measurement written into the same stream) and must not enter the
    streak. Mirrors #1790's ``story_snapshots``.
    """
    return [entry for entry in history if entry.get("batch")]


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def _yield_of(record: dict) -> int | None:
    """Net survivors killed by this batch, or ``None`` when unmeasurable."""
    start = _as_number(record.get("starting_survivors"))
    end = _as_number(record.get("ending_survivors"))
    if start is None or end is None:
        return None
    return int(start - end)


def _score_movement(record: dict) -> float | None:
    before = _as_number(record.get("honest_score_before"))
    after = _as_number(record.get("honest_score_after"))
    if before is None or after is None:
        return None
    return round(after - before, _SCORE_PRECISION)


def _batch_rows(records: list[dict]) -> list[dict]:
    return [
        {
            "batch": record.get("batch"),
            "module": record.get("module"),
            "captured_at": record.get("captured_at"),
            "starting_survivors": record.get("starting_survivors"),
            "ending_survivors": record.get("ending_survivors"),
            "rounds_spent": record.get("rounds_spent"),
            "kills": _yield_of(record),
            "score_movement": _score_movement(record),
        }
        for record in records
    ]


def _trailing_flat_streak(rows: list[dict], min_kills: int) -> list[dict]:
    """The trailing run of batches whose measured yield is below the minimum.

    Stops at the first batch that yielded enough OR whose yield is
    unmeasurable — an unmeasured batch breaks the streak rather than
    extending it.
    """
    streak: list[dict] = []
    for row in reversed(rows):
        kills = row["kills"]
        if kills is None or kills >= min_kills:
            break
        streak.append(row)
    streak.reverse()
    return streak


def evaluate(
    records: list[dict],
    min_kills: int = DEFAULT_MIN_KILLS,
    consecutive: int = DEFAULT_CONSECUTIVE,
) -> dict:
    """Evaluate batch-attributed ``records`` for a flat mutation-yield streak."""
    rows = _batch_rows(records)
    measured = [r for r in rows if r["kills"] is not None]
    streak = _trailing_flat_streak(rows, min_kills)

    if len(streak) >= consecutive:
        status = STATUS_FLAT
        message = (
            f"{len(streak)} consecutive batches killed fewer than {min_kills} "
            "survivor(s) ("
            + ", ".join(f"{r['batch']}: {r['kills']:+}" for r in streak)
            + "). Re-read coverage-gap-ranking.json and re-order the remaining "
            "batches before spending another mutation-kill dispatch — further "
            "rounds on this module are not converting into kills."
        )
    elif len(measured) < consecutive:
        status = STATUS_INSUFFICIENT
        message = (
            f"{len(measured)} batch yield(s) measured; {consecutive} are needed "
            "before a flat-yield streak can be judged."
        )
    elif rows[-1]["kills"] is None:
        # The trailing batch carries no usable survivor counts, so its yield
        # could not be measured. Neither `ok` nor `flat_streak` is honest here.
        status = STATUS_INSUFFICIENT
        message = (
            f"The latest batch ({rows[-1]['batch']}) could not be measured — "
            "its record carries no comparable survivor counts, so no yield "
            "verdict is possible for it."
        )
    elif streak:
        # Below the streak threshold but still not killing: reporting this as
        # `ok` would claim "mutation-kill is producing kills" about a batch
        # that killed less than the minimum — the false all-clear this gate
        # exists to prevent. Exit code stays 0; only the wording and status
        # carry the warning.
        status = STATUS_FORMING
        message = (
            f"The latest {len(streak)} batch/batches killed fewer than "
            f"{min_kills} survivor(s) ({len(streak)} of {consecutive} needed "
            "for a flat-yield streak). Watch the next batch's yield before "
            "spending more of the phase on this module."
        )
    else:
        status = STATUS_OK
        message = (
            f"Latest batch killed {rows[-1]['kills']} survivor(s) — "
            "mutation-kill is converting rounds into kills."
        )

    average = (
        round(sum(r["kills"] for r in measured) / len(measured), 2) if measured else None
    )
    return {
        "status": status,
        "batches_evaluated": len(rows),
        "batches_measured": len(measured),
        "min_kills": min_kills,
        "consecutive_threshold": consecutive,
        "streak": len(streak),
        "flat_batches": streak,
        "running_average_kills": average,
        "batches": rows,
        "message": message,
    }


def render_text(result: dict) -> str:
    lines = [
        f"Mutation-yield steering: {result['status']}",
        result["message"],
        "",
        (
            f"{'batch':<24}  {'start':>6}  {'end':>6}  {'kills':>6}  "
            f"{'rounds':>6}  {'Δ score':>8}"
        ),
    ]
    for row in result["batches"]:
        kills = row["kills"]
        move = row["score_movement"]
        lines.append(
            f"{row['batch']!s:<24}  "
            f"{row['starting_survivors'] if row['starting_survivors'] is not None else '-':>6}  "
            f"{row['ending_survivors'] if row['ending_survivors'] is not None else '-':>6}  "
            f"{kills if kills is not None else '-':>6}  "
            f"{row['rounds_spent'] if row['rounds_spent'] is not None else '-':>6}  "
            f"{move if move is not None else '-':>8}"
        )
    lines.append("")
    lines.append(f"running average kills per batch: {result['running_average_kills']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutation_yield_steering.py",
        description=(
            "Flag several consecutive mutation-kill batches whose net yield is "
            "near zero, so Phase-1 targeting can be re-checked mid-phase."
        ),
    )
    parser.add_argument(
        "--history",
        type=Path,
        required=True,
        help="Path to mutation-history.json.",
    )
    parser.add_argument(
        "--min-kills",
        type=int,
        default=DEFAULT_MIN_KILLS,
        help=(
            "Minimum expected net survivors killed per batch "
            f"(default: {DEFAULT_MIN_KILLS})."
        ),
    )
    parser.add_argument(
        "--consecutive",
        type=int,
        default=DEFAULT_CONSECUTIVE,
        help=(
            "How many consecutive below-minimum batches constitute a flat "
            f"streak (default: {DEFAULT_CONSECUTIVE})."
        ),
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    # An out-of-range threshold must fail loudly rather than produce a nonsense
    # verdict: `--consecutive 0` makes `len(streak) >= consecutive` trivially
    # true for any history (including an empty one), and `--min-kills 0` makes
    # every batch — including one that ADDED survivors — count as progress.
    if args.consecutive < 1:
        parser.error("--consecutive must be >= 1")
    if args.min_kills < 1:
        parser.error("--min-kills must be >= 1")

    try:
        history = load_history(args.history)
    except HistoryError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = evaluate(
        batch_records(history),
        min_kills=args.min_kills,
        consecutive=args.consecutive,
    )
    print(json.dumps(result, indent=2) if args.json else render_text(result))
    return 3 if result["status"] == STATUS_FLAT else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
