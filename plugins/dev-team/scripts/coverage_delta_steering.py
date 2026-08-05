#!/usr/bin/env python3
"""coverage_delta_steering.py — turn per-Story coverage deltas into a live
Phase-5 steering signal (issue #1790).

Why this exists. `/coverage-delta` already records one snapshot per Story into
`coverage-history.json`, but nothing read that history *during* the phase: a
Pass-1 run kept closing Stories and reporting mutation-kill progress while
line coverage stayed flat at 74.2%, and nobody saw it until the final report —
by which point the phase's whole budget had gone into the wrong layer. This
script is the mid-phase check: after each Story's delta lands, it measures the
movement of the trailing Stories and fails (exit 3) once several consecutive
Stories have moved line coverage by less than the minimum expected per-Story
delta, so `/test-improve` can prompt for a Phase-1 targeting re-check before
spending the next Story.

Movement, per Story snapshot, is the change in `line_pct` since the previous
Story snapshot — or, for the first Story, since the run's
`baseline_line_pct`. A **negative** movement counts as flat: a Story that made
coverage worse is certainly not progress. A snapshot with no comparable
predecessor (no previous Story and no recorded baseline) has movement `None`
and **breaks** the streak rather than extending it — absence of measurement is
not evidence of flatness.

Branch movement is reported alongside but does **not** drive the verdict:
branch coverage is not natively available on every stack (Go), so keying the
gate on it would make the check silently mode-dependent.

Statuses (and exit codes):

- `flat_streak` (3) — `--consecutive` or more trailing Stories each moved less
  than `--min-line-delta`. The caller prompts; this script does not decide
  policy.
- `flat_streak_forming` (0) — the trailing Story moved less than the minimum
  but the streak is still shorter than `--consecutive`. A distinct status
  rather than `ok`, because "not yet a streak" is not "coverage is moving".
- `insufficient_history` (0) — fewer measurable Stories than `--consecutive`,
  or a trailing Story whose movement could not be measured at all, so no
  streak verdict is possible yet.
- `ok` (0) — the trailing Story moved coverage by at least the minimum.
- exit `2` — the history file is missing, unreadable, not JSON, not a JSON
  array, or carries a non-snapshot element; also an out-of-range
  `--consecutive`/`--min-line-delta`. Never reported as an all-clear.

Stdlib-only (ADR 0014/0015), Python 3.10+ floor (ADR 0031).

Usage:
    python3 coverage_delta_steering.py \\
      --history .dev-team-reports/test-improve/<slug>/data/coverage-history.json
    python3 coverage_delta_steering.py --history <path> \\
      --min-line-delta 0.25 --consecutive 3 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MIN_LINE_DELTA = 0.1
DEFAULT_CONSECUTIVE = 3

STATUS_FLAT = "flat_streak"
STATUS_FORMING = "flat_streak_forming"
STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_history"

# Movements are rounded only to kill binary-float artifacts (72.4 - 72.0 =
# 0.40000000000000568), NOT to two decimals: rounding to 2dp before the
# threshold comparison would let a true 0.096-point move clear a 0.1 minimum,
# making a display concern decide the gate.
_MOVEMENT_PRECISION = 10


class HistoryError(ValueError):
    """The coverage history could not be read or is not a snapshot array."""


def load_history(path: Path) -> list[dict]:
    """Read `coverage-history.json`, raising HistoryError on anything that is
    not a readable JSON array of snapshot objects."""
    if not path.is_file():
        raise HistoryError(f"coverage history not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryError(f"{path}: unreadable coverage history ({exc})") from exc
    if not isinstance(payload, list):
        raise HistoryError(
            f"{path}: coverage history must be a JSON array of snapshots, "
            f"got {type(payload).__name__}"
        )
    # A non-dict element means the file is corrupt or half-rewritten. Dropping
    # it silently would leave a corrupt history indistinguishable from a phase
    # that simply hasn't closed enough Stories yet — a clean verdict from
    # unusable evidence, which is the one thing this gate must never produce.
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise HistoryError(
                f"{path}: coverage history entry at index {index} is a "
                f"{type(entry).__name__}, not a snapshot object"
            )
    return list(payload)


def story_snapshots(history: list[dict]) -> list[dict]:
    """Keep only Story-attributed snapshots — the per-Story Phase-5 deltas.
    Phase-less snapshots (`/quality-targets-converge`'s whole-suite call
    passes no `--story`) are not Stories and must not enter the streak."""
    return [entry for entry in history if entry.get("story")]


def _movement(current: object, previous: object) -> float | None:
    if isinstance(current, bool) or isinstance(previous, bool):
        return None
    if not isinstance(current, (int, float)) or not isinstance(previous, (int, float)):
        return None
    return round(float(current) - float(previous), _MOVEMENT_PRECISION)


def _story_rows(snapshots: list[dict]) -> list[dict]:
    rows = []
    for index, snapshot in enumerate(snapshots):
        if index == 0:
            prev_line = snapshot.get("baseline_line_pct")
            prev_branch = snapshot.get("baseline_branch_pct")
        else:
            prev_line = snapshots[index - 1].get("line_pct")
            prev_branch = snapshots[index - 1].get("branch_pct")
        rows.append(
            {
                "story": snapshot.get("story"),
                "captured_at": snapshot.get("captured_at"),
                "line_pct": snapshot.get("line_pct"),
                "branch_pct": snapshot.get("branch_pct"),
                "line_movement": _movement(snapshot.get("line_pct"), prev_line),
                "branch_movement": _movement(snapshot.get("branch_pct"), prev_branch),
            }
        )
    return rows


def _trailing_flat_streak(rows: list[dict], min_line_delta: float) -> list[dict]:
    """The trailing run of Stories whose measured line movement is below the
    minimum. Stops at the first Story that moved enough OR whose movement is
    unmeasurable."""
    streak: list[dict] = []
    for row in reversed(rows):
        movement = row["line_movement"]
        if movement is None or movement >= min_line_delta:
            break
        streak.append(row)
    streak.reverse()
    return streak


def evaluate(
    snapshots: list[dict],
    min_line_delta: float = DEFAULT_MIN_LINE_DELTA,
    consecutive: int = DEFAULT_CONSECUTIVE,
) -> dict:
    """Evaluate Story-attributed `snapshots` for a flat-coverage streak."""
    rows = _story_rows(snapshots)
    measured = [r for r in rows if r["line_movement"] is not None]
    streak = _trailing_flat_streak(rows, min_line_delta)

    if len(streak) >= consecutive:
        status = STATUS_FLAT
        message = (
            f"{len(streak)} consecutive Stories moved line coverage by less than "
            f"{min_line_delta} points ("
            + ", ".join(f"{r['story']}: {r['line_movement']:+}" for r in streak)
            + "). Re-check Phase-1 targeting against "
            "coverage-gap-ranking.json before spending the next Story — "
            "mutation-kill progress on an already-covered layer cannot move "
            "these numbers."
        )
    elif len(measured) < consecutive:
        status = STATUS_INSUFFICIENT
        message = (
            f"{len(measured)} Story delta(s) measured; {consecutive} are needed "
            "before a flat-coverage streak can be judged."
        )
    elif rows[-1]["line_movement"] is None:
        # The trailing Story has no comparable predecessor (a null/absent
        # line_pct in the appended snapshot), so its movement could not be
        # measured. Neither `ok` nor `flat_streak` is honest here.
        status = STATUS_INSUFFICIENT
        message = (
            f"The latest Story ({rows[-1]['story']}) could not be measured — "
            "its snapshot carries no comparable line_pct, so no coverage "
            "movement verdict is possible for it."
        )
    elif streak:
        # Below the streak threshold but still not moving: reporting this as
        # `ok` would claim "targeting is producing coverage movement" about a
        # Story that moved less than the minimum — the false all-clear this
        # gate exists to prevent. Exit code stays 0; only the wording and
        # status carry the warning.
        status = STATUS_FORMING
        message = (
            f"The latest {len(streak)} Story/Stories moved line coverage by less "
            f"than {min_line_delta} points ({len(streak)} of {consecutive} "
            "needed for a flat-coverage streak). Watch the next Story's delta "
            "before spending more of the phase on this layer."
        )
    else:
        status = STATUS_OK
        message = (
            f"Latest Story moved line coverage by "
            f"{rows[-1]['line_movement']:+} points — targeting is producing "
            "coverage movement."
        )

    average = (
        round(sum(r["line_movement"] for r in measured) / len(measured), 2)
        if measured
        else None
    )
    return {
        "status": status,
        "stories_evaluated": len(rows),
        "stories_measured": len(measured),
        "min_line_delta": min_line_delta,
        "consecutive_threshold": consecutive,
        "streak": len(streak),
        "flat_stories": streak,
        "running_average_line_movement": average,
        "stories": rows,
        "message": message,
    }


def render_text(result: dict) -> str:
    lines = [
        f"Coverage-delta steering: {result['status']}",
        result["message"],
        "",
        f"{'story':<24}  {'line %':>8}  {'Δ line':>8}  {'Δ branch':>9}",
    ]
    for row in result["stories"]:
        line_move = row["line_movement"]
        branch_move = row["branch_movement"]
        lines.append(
            f"{row['story']!s:<24}  "
            f"{row['line_pct'] if row['line_pct'] is not None else '-':>8}  "
            f"{line_move if line_move is not None else '-':>8}  "
            f"{branch_move if branch_move is not None else '-':>9}"
        )
    lines.append("")
    lines.append(
        f"running average line movement: {result['running_average_line_movement']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coverage_delta_steering.py",
        description=(
            "Flag several consecutive Stories whose coverage delta is "
            "near zero, so Phase-1 targeting can be re-checked mid-phase."
        ),
    )
    parser.add_argument(
        "--history",
        type=Path,
        required=True,
        help="Path to coverage-history.json.",
    )
    parser.add_argument(
        "--min-line-delta",
        type=float,
        default=DEFAULT_MIN_LINE_DELTA,
        help=(
            "Minimum expected per-Story line-coverage movement in percentage "
            f"points (default: {DEFAULT_MIN_LINE_DELTA})."
        ),
    )
    parser.add_argument(
        "--consecutive",
        type=int,
        default=DEFAULT_CONSECUTIVE,
        help=(
            "How many consecutive below-minimum Stories constitute a flat "
            f"streak (default: {DEFAULT_CONSECUTIVE})."
        ),
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    # An out-of-range threshold must fail loudly rather than produce a nonsense
    # verdict: `--consecutive 0` makes `len(streak) >= consecutive` trivially
    # true for any history (including an empty one), and a negative
    # `--min-line-delta` makes every movement — regressions included — count
    # as progress.
    if args.consecutive < 1:
        parser.error("--consecutive must be >= 1")
    if args.min_line_delta < 0:
        parser.error("--min-line-delta must be >= 0")

    try:
        history = load_history(args.history)
    except HistoryError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = evaluate(
        story_snapshots(history),
        min_line_delta=args.min_line_delta,
        consecutive=args.consecutive,
    )
    print(json.dumps(result, indent=2) if args.json else render_text(result))
    return 3 if result["status"] == STATUS_FLAT else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
