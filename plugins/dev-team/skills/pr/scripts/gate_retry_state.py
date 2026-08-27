#!/usr/bin/env python3
"""Across-invocation `/pr` gate scoping — the fix-diff retry loop (#2087).

## The gap this closes

`/code-review`'s own round ledger (`../code-review/scripts/finding_signature.py`,
#1625) and closing pass (`../code-review/scripts/closing_pass.py`, #1626)
already scope a review down to the fix delta — but strictly *within one*
`/code-review` invocation's own internal fix loop (up to `MAX_ITERATIONS=5`).
`finding_signature.py`'s own reset-trigger table is explicit that "round 1
always starts a new run": every NEW top-level `/code-review` call — including
a second `/pr` invocation run after a human manually fixes something outside
code-review's own automatic loop — restarts at round 1 with the FULL
branch-diff panel, whatever narrower scoping the previous invocation had
converged to.

That is the actual mechanism PR #2085 paid for: `/pr`'s Step 2 gate calls
`/code-review --since <merge-base> --json` exactly once per `/pr` invocation,
unconditionally at full-branch scope. Two separate `/pr` runs (Round B and
Round C) each re-scanned all 10 changed files with a 6-8 finder-agent fleet,
even though the only thing that had changed since the prior round was the fix
applied in direct response to that prior round's own findings. Reconstructed
cost for that one PR's review rounds: ~$242 across 91 subagent dispatches.

## What this module is

A deterministic transition function — no LLM judgment — callable once per
`/pr` Step-2 gate check, that decides what git ref to hand `/code-review
--since <ref>` next, and whether the retry budget for this PR is exhausted.
State persists in a JSON file across separate `/pr` invocations (mirroring
where `../code-review/scripts/finding_signature.py`'s
`review-round-state.json` already lives), so a second `/pr` run on the same
branch narrows to just the fix delta instead of re-scanning everything.

The phase machine has four states: `initial` (first, full-branch check) ->
`fix-diff` (narrow re-check after a `fail`) -> `confirm` (one mandatory
full-branch pass before the gate can close, issue #2087's requirement 3) ->
`done`. A `fail` from any phase routes back to `fix-diff` — see `decide()`'s
"pass or warn" branch, which is the only place `phase` advances forward.

## Design mirrors `finding_signature.py`, deliberately not imported

Same four-trigger, precedence-ordered, "fails toward a reset" reset-trigger
table; same round-cap posture; the TTL and round-cap constants below are
independently defined and cross-checked for drift in
`plugins/dev-team/tests/scripts/test_gate_retry_state.py`, exactly like
`closing_pass.py`'s `MIN_DISTINCT_DISPATCHES` is checked against
`hooks/pre_pr_review.py`. This script must not import across skill
directories — a future change to either skill's constant fails a test rather
than silently drifting the other.

## Why the "no `--last-outcome`" call still writes a placeholder

The first call of a `/pr` invocation (no `--last-outcome` yet) reports a
scope without "committing" a new round — no round increment, no recorded
outcome. But if that call is a genuinely fresh start (no prior state, or the
prior run's own gate already reached `done`), it *does* persist a minimal
placeholder (`round=1, phase="initial"`) so that a crash between this call
and the `--last-outcome` call that would normally follow it (`/code-review`
itself dying mid-run, the session ending) leaves evidence on disk: the next
invocation's first call resumes at the same round/scope instead of silently
losing the fact that a full-branch check was already attempted. See
`compute_pending()`'s `phase == "initial"` branch, which exists solely to
serve this resumed-but-never-recorded case.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Total dispatch rounds after which the retry loop stops advancing
#: automatically and hands control back to a human — no further `/pr`
#: invocation narrows the scope on its own. Same value and reasoning as
#: `../code-review/scripts/finding_signature.py`'s `MAX_ROUNDS` (initial +
#: 3 more); independently defined so a change to one doesn't silently
#: desync from the other. Drift-tested in
#: `plugins/dev-team/tests/scripts/test_gate_retry_state.py`.
PR_GATE_MAX_ROUNDS = 4

#: A stored gate-retry state older than this is discarded rather than
#: reused — the same 24h reasoning as `finding_signature.STATE_TTL_SECONDS`:
#: a `/pr` gate check does not legitimately span a day, so a state file that
#: old is abandoned residue. Independently defined; drift-tested alongside
#: `PR_GATE_MAX_ROUNDS` above.
PR_GATE_STATE_TTL_SECONDS = 24 * 60 * 60

_OUTCOMES = frozenset({"pass", "warn", "fail"})

_DEFAULT_STATE_PATH = ".claude/memory/pr-gate-state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(iso) -> float | None:
    try:
        stamp = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def _load_state(state_path, branch: str, base_sha: str, force_reset: bool):
    """Load the persisted gate-retry state, discarding it when it can't be
    safely resumed. Returns `(state_or_None, reset_reason)`; `state_or_None`
    is `None` whenever this run must start fresh, and `reset_reason` is
    `None` only when nothing anomalous happened (no file at all, or a
    legitimately resumed run).

    Four reset triggers, in precedence order — mirrors
    `finding_signature._load_state`'s table and its "fails toward a reset"
    philosophy: an ambiguous or stale state always restarts full-branch
    rather than risking a narrow scope that silently misses something.

    1. `--reset` — explicit, caller-forced.
    2. Stored `branch` differs from the current branch — belongs to a
       different `/pr` run entirely (a fresh branch, or history from a
       branch reused for something else).
    3. Stored `base_sha` differs from the current merge-base — the base
       moved (rebase, or the target branch advanced) since the last check;
       "only what changed since `last_reviewed_sha`" no longer holds safely
       against a shifted base.
    4. Staleness — `PR_GATE_STATE_TTL_SECONDS` since the run started.

    A missing state file is not itself a "reset" (nothing was there to
    reset) — it returns `(None, None)`, the same as `finding_signature`'s
    round-1 case, and is handled as a fresh start by `compute_pending()`.
    """
    if force_reset:
        return None, "explicit-reset"
    if state_path is None or not state_path.is_file():
        return None, None

    try:
        stored = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "unreadable-state"
    if not isinstance(stored, dict):
        return None, "unreadable-state"

    if stored.get("branch") != branch:
        return None, "branch-mismatch"
    if stored.get("base_sha") != base_sha:
        return None, "base-sha-mismatch"

    age = _age_seconds(stored.get("started_at"))
    if age is not None and age > PR_GATE_STATE_TTL_SECONDS:
        return None, "stale-state"

    return stored, None


def compute_pending(stored, base_sha: str) -> dict:
    """Decide the scope for the round about to run (or that just ran),
    purely from persisted state — never mutates `stored`, never touches
    disk. `stored` is `None` (or a leftover `phase == "done"` record — see
    module docstring's note on why that should not normally happen) for a
    fresh start: round 1, full-branch scope.

    A `phase == "initial"` resumed state is the crash-recovery case: the
    previous `/pr` invocation's first call decided a full-branch check but
    never got to record its outcome. Repeating `since_ref = base_sha` at the
    same round is correct — the full-branch check never actually completed,
    so jumping to a narrower `fix-diff` scope would silently skip reviewing
    parts of the branch.
    """
    if stored is None or stored.get("phase") == "done":
        return {"phase": "initial", "round": 1, "since_ref": base_sha, "escalate": False}

    round_ = stored.get("round", 1)
    phase = stored.get("phase", "initial")

    if round_ >= PR_GATE_MAX_ROUNDS:
        return {"phase": phase, "round": round_, "since_ref": None, "escalate": True}

    if phase == "fix-diff":
        since_ref = stored.get("last_reviewed_sha") or base_sha
    else:  # "initial" (crash-recovery resume) or "confirm"
        since_ref = base_sha

    return {"phase": phase, "round": round_, "since_ref": since_ref, "escalate": False}


def decide(stored, reset_reason, branch: str, base_sha: str, head_sha: str, last_outcome):
    """The transition function. Returns `(result, new_state_or_None, delete)`
    — `result` is the JSON payload to print; `new_state_or_None` is what to
    persist (or `None` for "leave disk untouched"); `delete` is `True` when
    the caller must remove the state file instead (the `done` transitions).

    See the module docstring for the phase machine and the CLI contract in
    `main()`'s argparse help for the two call shapes (no `--last-outcome`
    vs. `--last-outcome given`).
    """
    pending = compute_pending(stored, base_sha)

    if last_outcome is None:
        # First call of a /pr invocation: report the scope this round should
        # use. No round is "committed" here — see the module docstring's
        # note on why a genuinely fresh start still persists a placeholder.
        result = {
            "since_ref": pending["since_ref"],
            "phase": pending["phase"],
            "round": pending["round"],
            "reset_reason": reset_reason,
            "escalate": pending["escalate"],
        }
        is_fresh_start = stored is None or stored.get("phase") == "done"
        new_state = None
        if is_fresh_start:
            new_state = {
                "branch": branch,
                "base_sha": base_sha,
                "last_reviewed_sha": None,
                "round": 1,
                "phase": "initial",
                "started_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        return result, new_state, False

    # --last-outcome given: record the result of the call this call's
    # `pending` describes, then transition.
    if pending["escalate"]:
        # Misuse guard: the retry budget was already exhausted before this
        # call (a caller ignored the previous escalate=true and dispatched
        # /code-review again anyway). Do not advance the round further.
        result = {
            "since_ref": None,
            "phase": pending["phase"],
            "round": pending["round"],
            "reset_reason": reset_reason,
            "escalate": True,
        }
        return result, None, False

    new_round = pending["round"] + 1
    started_at = (stored or {}).get("started_at") or _now_iso()

    if last_outcome == "fail":
        new_state = {
            "branch": branch,
            "base_sha": base_sha,
            "last_reviewed_sha": head_sha,
            "round": new_round,
            "phase": "fix-diff",
            "started_at": started_at,
            "updated_at": _now_iso(),
        }
        # Re-derive the returned scope from the state just persisted so the
        # round-cap check (escalate) is computed exactly once, in
        # compute_pending(), rather than duplicated here.
        next_pending = compute_pending(new_state, base_sha)
        result = {
            "since_ref": next_pending["since_ref"],
            "phase": next_pending["phase"],
            "round": next_pending["round"],
            "reset_reason": reset_reason,
            "escalate": next_pending["escalate"],
        }
        return result, new_state, False

    # pass or warn: converged for the scope `pending` described.
    converged_phase = pending["phase"]
    if converged_phase in ("initial", "confirm"):
        # Full-branch check passed (either the very first one, or the
        # mandatory pre-merge confirm) — nothing left to review.
        result = {
            "since_ref": None,
            "phase": "done",
            "round": new_round,
            "reset_reason": reset_reason,
            "escalate": False,
        }
        return result, None, True

    # converged_phase == "fix-diff": issue #2087's requirement 3 — one
    # mandatory full-branch confirmation before the gate can close, run
    # immediately in the same /pr invocation (see pr/SKILL.md step 2).
    new_state = {
        "branch": branch,
        "base_sha": base_sha,
        "last_reviewed_sha": head_sha,
        "round": new_round,
        "phase": "confirm",
        "started_at": started_at,
        "updated_at": _now_iso(),
    }
    result = {
        "since_ref": base_sha,
        "phase": "confirm",
        "round": new_round,
        "reset_reason": reset_reason,
        "escalate": False,
    }
    return result, new_state, False


def _write_state(state_path: Path, data: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _delete_state(state_path: Path) -> None:
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Decide /pr Step 2's next `/code-review --since <ref>` scope "
            "and whether the gate-retry budget is exhausted (#2087)."
        )
    )
    parser.add_argument(
        "--state",
        default=_DEFAULT_STATE_PATH,
        help=f"Path to the durable gate-retry state file (default: {_DEFAULT_STATE_PATH})",
    )
    parser.add_argument("--branch", required=True, help="Current branch name")
    parser.add_argument(
        "--base-sha", required=True, dest="base_sha", help="Current merge-base sha"
    )
    parser.add_argument("--head-sha", required=True, dest="head_sha", help="Current HEAD sha")
    parser.add_argument(
        "--last-outcome",
        choices=sorted(_OUTCOMES),
        default=None,
        dest="last_outcome",
        help=(
            "Omit on the first call of a /pr invocation. Pass on every call "
            "after a /code-review result is known, to record it and "
            "transition to the next scope."
        ),
    )
    parser.add_argument(
        "--reset", action="store_true", help="Discard any stored state and start a fresh run."
    )
    args = parser.parse_args(argv)

    state_path = Path(args.state) if args.state else None
    stored, reset_reason = _load_state(state_path, args.branch, args.base_sha, args.reset)

    result, new_state, delete = decide(
        stored, reset_reason, args.branch, args.base_sha, args.head_sha, args.last_outcome
    )

    if state_path is not None:
        if delete:
            _delete_state(state_path)
        elif new_state is not None:
            _write_state(state_path, new_state)

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
