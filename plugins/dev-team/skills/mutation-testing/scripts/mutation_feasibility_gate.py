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

``ask-operator`` is also the arbiter's answer when the detector found
shim-breaking xunit.v3 constructs (#1791). That used to be a pure time-budget
question, which meant the operator's real decision — port, exclude, skip, or
degrade — was never presented anywhere; the shim was silently built, declined,
or degraded and they found out from a report, if at all. Feeding the detector's
findings in through ``ProbeResult.v3_blockers`` makes the same decision point
carry the per-construct breakdown plus those four options (built and rendered
by ``hooks/lib/xunit_v3_operator_gate.py``, so the guard hook and this gate
present one story).

Fail-closed on an omitted ``--v3-findings-json`` (#1870): every caller of this
CLI is, by the calling convention, already on an xunit.v3 project — "plain
xunit.v2 / other stacks skip this gate" per ``agents/mutation-kill.md``. Before
this fix, omitting the flag silently meant "no blockers" (``_load_v3_findings``
returned an empty tuple indistinguishable from "the detector ran and found
none"), so a caller that forgot to run the detector — or wired it up wrong —
got ``enter-loop`` with no operator question ever asked, the exact silent
decision #1791 exists to stop. ``ProbeResult.v3_findings_known`` (default
``True``, so direct ``decide()`` callers that already know their own
"no blockers" state are unaffected) is ``False`` only when the CLI itself
observed the flag was never supplied; :func:`decide` then forces
``ask-operator`` with a reason naming the missing detector run, combined with
the budget signal exactly like a real blocker set would be.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import enum
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

# skills/mutation-testing/scripts -> skills/mutation-testing -> skills
# -> plugin root -> hooks/lib
_HOOKS_LIB_DIR = Path(__file__).resolve().parents[3] / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import xunit_v3_operator_gate as _operator_gate  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    _operator_gate = None


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

# #1870: the reason surfaced when `ProbeResult.v3_findings_known` is False —
# the CLI never consulted the shim-breaking-construct detector for this
# xunit.v3 project, so entering the loop would be a guess, not a decision.
_V3_FINDINGS_UNKNOWN_REASON = (
    "the xunit.v3 shim-breaking-construct detector output (--v3-findings-json) "
    "was not supplied for this xunit.v3 project (#1870) — cannot rule out "
    "shim-breaking constructs without it; run xunit_v3_feature_detector.py or "
    "confirm none apply"
)


def _clamp_budget_seconds(budget_seconds: float) -> float:
    """Clamp a non-positive budget back to ``DEFAULT_ROUND_BUDGET_SECONDS``.

    Shared by :func:`resolve_budget_seconds` (env-sourced) and
    :func:`decide` (an explicit ``budget_seconds``/``--budget-seconds``
    override) so a non-positive value is treated identically regardless of
    which path it arrived by (#1549) — an explicit ``0``/negative override
    no longer silently bypasses the clamp and forces ``ASK_OPERATOR`` on
    every invocation."""
    return budget_seconds if budget_seconds > 0 else DEFAULT_ROUND_BUDGET_SECONDS


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
    return _clamp_budget_seconds(val)


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
    always travel together as one probe's result set, plus the detector's
    shim-breaking findings (#1791) when there are any.

    ``v3_blockers`` holds ``xunit_v3_feature_detector`` findings (its dataclass
    or its ``--json`` dict form). ``v3_unclassified_files`` holds files the
    guard hook's broader token scan flagged but the detector cannot classify —
    they must still reach the operator rather than being dropped for lacking a
    classification.
    """

    shim_declined: bool
    capture_failed: bool
    probe_seconds: float
    scope_file_count: int
    project: str = ""
    v3_blockers: tuple = field(default_factory=tuple)
    v3_unclassified_files: tuple = field(default_factory=tuple)
    #: False only when the caller has NOT actually consulted the detector for
    #: this xunit.v3 project (#1870) — e.g. the CLI's `--v3-findings-json` was
    #: omitted. Defaults True so a direct `decide(ProbeResult(...))` caller
    #: that already knows its own "detector ran, found nothing" state
    #: (`v3_blockers=()`) is unaffected; only the CLI sets this False.
    v3_findings_known: bool = True


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: str
    estimated_round_seconds: float | None = None
    budget_seconds: float | None = None
    #: The operator question payload (breakdown + the four remediation
    #: options) when v3 blockers drove an ``ask-operator``; None otherwise.
    question: dict | None = None

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


def _construct_of(finding) -> str:
    if isinstance(finding, dict):
        return str(finding.get("construct") or "")
    return str(getattr(finding, "construct", "") or "")


def _blocking_constructs(probe: ProbeResult) -> str:
    """The distinct construct names, for the ``ask-operator`` reason line."""
    names: list[str] = []
    for finding in probe.v3_blockers:
        name = _construct_of(finding)
        if name and name not in names:
            names.append(name)
    if probe.v3_unclassified_files:
        names.append("unclassified")
    return ", ".join(names) or "unclassified"


def build_operator_question(probe: ProbeResult) -> dict | None:
    """The operator question payload for ``probe``, or None when nothing blocks.

    Delegates to ``hooks/lib/xunit_v3_operator_gate.py`` so this gate and the
    ``stryker_xunit_shim_guard`` PreToolUse hook cannot drift into telling the
    operator two different stories. If that library is unreachable the gate
    still ASKS — with a degraded payload naming the files — rather than
    proceeding as if nothing blocked.
    """
    if not (probe.v3_blockers or probe.v3_unclassified_files):
        return None
    project = probe.project or "the test project"
    if _operator_gate is None:  # pragma: no cover - degraded fallback
        return {
            "project": project,
            "headline": (
                f"shim-breaking xunit.v3 constructs in '{project}' "
                f"({_blocking_constructs(probe)})"
            ),
            "degraded": True,
            "unclassified_files": list(probe.v3_unclassified_files),
        }
    question = _operator_gate.build_question(
        project, probe.v3_blockers, probe.v3_unclassified_files
    )
    return question.as_dict() if question.blocking else None


def render_operator_question(probe: ProbeResult) -> str:
    """The operator-facing text for ``probe``'s blockers (empty when none).

    Rendered from the probe rather than from :func:`build_operator_question`'s
    dict so the per-finding line numbers survive into the text the operator
    actually reads.
    """
    if _operator_gate is None:  # pragma: no cover - degraded fallback
        return ""
    if not (probe.v3_blockers or probe.v3_unclassified_files):
        return ""
    question = _operator_gate.build_question(
        probe.project or "the test project",
        probe.v3_blockers,
        probe.v3_unclassified_files,
    )
    return "\n".join(_operator_gate.render_question(question))


def decide(probe: ProbeResult, *, budget_seconds: float | None = None) -> Decision:
    """Arbitrate between entering the loop, asking the operator, or degrading
    from the shim-first probe.

    Order matters: an operator's decline and a hard capture failure both make
    the loop infeasible regardless of timing, so they short-circuit before the
    (timing-based) budget check — which itself only means anything once per-test
    capture is known to work. Shim-breaking v3 constructs sit between the two:
    they are not a hard blocker (the operator has four ways out), so they ask
    rather than degrade — but they take precedence over the budget question, and
    when both fire the operator gets ONE decision point stating blockers and
    timing together rather than a blockers question that hides an unaffordable
    round.
    """
    if budget_seconds is None:
        budget_seconds = resolve_budget_seconds()
    else:
        budget_seconds = _clamp_budget_seconds(budget_seconds)

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

    question = build_operator_question(probe)

    if question is None and not probe.v3_findings_known:
        # #1870: the detector was never consulted for this xunit.v3 project —
        # unlike a real, already-classified blocker/unclassified set (handled
        # by `question is not None` below), there is nothing to build a
        # question FROM here, only the fact that nobody asked the detector.
        # Fail closed rather than silently proceeding as if it had found
        # nothing. Same over-budget combination as a real blocker set below,
        # so the operator gets one decision point, not two.
        over_budget = estimated > budget_seconds
        reason = _V3_FINDINGS_UNKNOWN_REASON
        if over_budget:
            reason += (
                f"; the estimated round {estimated:.0f}s also exceeds the "
                f"{budget_seconds:.0f}s budget"
            )
        return Decision(
            Outcome.ASK_OPERATOR,
            reason,
            estimated_round_seconds=estimated,
            budget_seconds=budget_seconds,
        )

    if question is not None:
        over_budget = estimated > budget_seconds
        reason = (
            f"shim-breaking xunit.v3 constructs found ({_blocking_constructs(probe)}) "
            "— the operator must choose port / exclude / skip / degrade before the "
            "shim path proceeds (#1791, gate #1160)"
        )
        if over_budget:
            reason += (
                f"; the estimated round {estimated:.0f}s also exceeds the "
                f"{budget_seconds:.0f}s budget"
            )
        return Decision(
            Outcome.ASK_OPERATOR,
            reason,
            estimated_round_seconds=estimated,
            budget_seconds=budget_seconds,
            question=question,
        )

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


def _load_v3_findings(source: str | None) -> tuple:
    """Read the detector's ``--json`` output into a findings tuple.

    Accepts the full ``{"findings": [...], "summary": {...}}`` object or a bare
    list. Raises ``OSError``/``ValueError``/``TypeError`` on anything
    unreadable — see the caller for why that must not silently become
    "no blockers".
    """
    if not source:
        return ()
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict):
        findings = data.get("findings")
    else:
        findings = data
    if findings is None:
        raise ValueError("no 'findings' key and not a bare findings list")
    if not isinstance(findings, list):
        raise TypeError(f"'findings' is {type(findings).__name__}, expected a list")
    return tuple(findings)


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
    parser.add_argument(
        "--project",
        default="",
        help="test project name (csproj stem) the v3 findings belong to",
    )
    parser.add_argument(
        "--v3-findings-json",
        default=None,
        help="xunit_v3_feature_detector.py --json output ('-' for stdin): either "
        "the full {findings, summary} object or a bare findings list",
    )
    parser.add_argument(
        "--v3-unclassified",
        action="append",
        default=[],
        help="a file flagged as v3-only that the detector could not classify "
        "(repeatable)",
    )
    args = parser.parse_args(list(argv))

    try:
        blockers = _load_v3_findings(args.v3_findings_json)
    except (OSError, ValueError, TypeError) as exc:
        # A detector output we cannot read must NOT be treated as "no blockers":
        # that would hand back enter-loop and skip the operator gate entirely,
        # which is the class of silent decision #1791 exists to stop.
        print(f"error: cannot read --v3-findings-json: {exc}", file=sys.stderr)
        return 2

    probe = ProbeResult(
        shim_declined=args.shim_declined,
        capture_failed=args.capture_failed,
        probe_seconds=args.probe_seconds,
        scope_file_count=args.scope_files,
        project=args.project,
        v3_blockers=blockers,
        v3_unclassified_files=tuple(args.v3_unclassified),
        # #1870: only the CLI can tell "omitted" apart from "provided, found
        # nothing" — every invocation of this CLI is for an xunit.v3 project
        # by calling convention, so omission must not silently read as
        # "known-empty".
        v3_findings_known=args.v3_findings_json is not None,
    )
    decision = decide(probe, budget_seconds=args.budget_seconds)
    payload = asdict(decision)
    payload["outcome"] = decision.outcome.value
    payload["waiver"] = decision.waiver
    if decision.question is not None:
        payload["question_text"] = render_operator_question(probe)
    print(json.dumps(payload, indent=2))
    # Exit 0 either way — this is an advisory arbiter, not a gate that fails a run.
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
