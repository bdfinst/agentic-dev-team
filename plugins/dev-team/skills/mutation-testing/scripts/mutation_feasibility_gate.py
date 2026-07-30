#!/usr/bin/env python3
"""Pre-loop feasibility gate for the mutant-kill loop (#1158, part of #1156).

The mutant-kill loop re-runs mutation after every generation round, so it is
only viable when a scoped run gets **per-test** coverage (covering-subset per
mutant). On an xunit.v3 suite that requires the v2 shim; if the shim path is
declined, or per-test coverage capture fails (#1157) so Stryker degrades to
whole-suite-per-mutant, or a single round would blow a wall-clock budget, then
looping is infeasible — pay the cost once as a single advisory pass, never loop.

This module is the pure, testable **arbiter**: given the shim-first one-file
probe's results it returns ``enter-loop``, ``degrade``, or ``ask-operator``
with a reason. A shim decline or a capture failure returns ``degrade``
unconditionally; an estimated round over budget with no other blocker returns
``ask-operator`` instead — a pure time estimate is not a hard blocker, so the
gate defers to the operator rather than degrading on its own. The agent runs
the probe (reusing the wrapper + #1157's capture detection) and feeds the
measurements here; applying the shim exclusions is #1159's job.

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import enum
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass


class Outcome(enum.Enum):
    """The three valid ``Decision.outcome`` values the arbiter can return."""

    ENTER_LOOP = "enter-loop"
    DEGRADE = "degrade"
    ASK_OPERATOR = "ask-operator"


# Wall-clock ceiling for a single estimated loop round. Not a magic constant on
# the probe side — the round estimate is *derived from the measured probe*
# (probe_seconds × scope files); this ceiling is the operator-tolerable maximum,
# overridable so slow-but-working environments degrade rather than grind.
DEFAULT_ROUND_BUDGET_SECONDS = 1800.0
_BUDGET_ENV = "DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS"

WAIVER_MESSAGE = (
    "mutant-kill loop not feasible on this suite (xunit.v3); ran single-pass "
    "advisory instead"
)


def resolve_budget_seconds(env: dict | None = None) -> float:
    """The per-round wall-clock ceiling — ``DEFAULT_ROUND_BUDGET_SECONDS``
    unless ``DEV_TEAM_MUTATION_ROUND_BUDGET_SECONDS`` overrides it. A
    non-positive or unparseable override falls back to the default."""
    src = os.environ if env is None else env
    raw = src.get(_BUDGET_ENV)
    if raw is None:
        return DEFAULT_ROUND_BUDGET_SECONDS
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_ROUND_BUDGET_SECONDS
    return val if val > 0 else DEFAULT_ROUND_BUDGET_SECONDS


def estimate_round_seconds(probe_seconds: float, scope_file_count: int) -> float:
    """Estimate one full loop round from the one-file probe. Under working
    per-test coverage each file costs ~the probe's wall-clock, so a round over
    N files is ~probe × N. Derived from the probe, never hardcoded."""
    if probe_seconds < 0:
        probe_seconds = 0.0
    return probe_seconds * max(1, scope_file_count)


@dataclass(frozen=True)
class ProbeResult:
    """The shim-first one-file probe's measurements — the four values that
    always travel together as one probe's result set."""

    shim_declined: bool
    capture_failed: bool
    probe_seconds: float
    scope_file_count: int


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: str
    estimated_round_seconds: float | None = None
    budget_seconds: float | None = None

    @property
    def waiver(self) -> str | None:
        """The precise waiver line to record when degrading; None when the
        loop is entered (no waiver needed) or when the operator still has to
        be asked (no waiver yet — pending operator input)."""
        if self.outcome is Outcome.ENTER_LOOP:
            return None
        if self.outcome is Outcome.ASK_OPERATOR:
            return None
        if self.outcome is Outcome.DEGRADE:
            return WAIVER_MESSAGE
        raise ValueError(f"unknown outcome: {self.outcome!r}")


def decide(probe: ProbeResult, *, budget_seconds: float | None = None) -> Decision:
    """Arbitrate between entering the loop, asking the operator, or degrading
    from the shim-first probe.

    Order matters: an operator's decline and a hard capture failure both make
    the loop infeasible regardless of timing, so they short-circuit before the
    (timing-based) budget check — which itself only means anything once per-test
    capture is known to work.
    """
    if budget_seconds is None:
        budget_seconds = resolve_budget_seconds()

    if probe.shim_declined:
        return Decision(
            Outcome.DEGRADE,
            "operator declined the shim path at the v3-feature gate (#1160)",
        )
    if probe.capture_failed:
        return Decision(
            Outcome.DEGRADE,
            "per-test coverage capture failed on the probe (#1157) — Stryker "
            "fell back to whole-suite-per-mutant, so each loop round pays the "
            "full-suite cost",
        )

    estimated = estimate_round_seconds(probe.probe_seconds, probe.scope_file_count)
    if estimated > budget_seconds:
        return Decision(
            Outcome.ASK_OPERATOR,
            f"estimated round {estimated:.0f}s exceeds the {budget_seconds:.0f}s "
            "budget (per-test works but the suite is too slow to iterate)",
            estimated_round_seconds=estimated,
            budget_seconds=budget_seconds,
        )
    return Decision(
        Outcome.ENTER_LOOP,
        f"per-test capture works and the estimated round {estimated:.0f}s is "
        f"within the {budget_seconds:.0f}s budget",
        estimated_round_seconds=estimated,
        budget_seconds=budget_seconds,
    )


def _cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Arbitrate the mutant-kill loop's shim-first feasibility gate."
    )
    parser.add_argument(
        "--shim-declined",
        action="store_true",
        help="operator declined the shim path at the #1160 v3-feature gate",
    )
    parser.add_argument(
        "--capture-failed",
        action="store_true",
        help="the #1157 coverage-capture-failure signal fired on the probe",
    )
    parser.add_argument(
        "--probe-seconds", type=float, default=0.0, help="measured one-file probe wall-clock"
    )
    parser.add_argument(
        "--scope-files", type=int, default=1, help="number of files in the loop scope"
    )
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=None,
        help="override the per-round wall-clock budget",
    )
    args = parser.parse_args(list(argv))

    probe = ProbeResult(
        shim_declined=args.shim_declined,
        capture_failed=args.capture_failed,
        probe_seconds=args.probe_seconds,
        scope_file_count=args.scope_files,
    )
    decision = decide(probe, budget_seconds=args.budget_seconds)
    payload = asdict(decision)
    payload["outcome"] = decision.outcome.value
    payload["waiver"] = decision.waiver
    print(json.dumps(payload, indent=2))
    # Exit 0 either way — this is an advisory arbiter, not a gate that fails a run.
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
