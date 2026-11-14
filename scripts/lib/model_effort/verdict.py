"""The stress matrix's verdict: move the agent one tier down, one tier up, or keep it.

`decide` is pure and works on per-arm tallies; `stress_verdict` tallies a run's
arms and applies the checks that block any tier change first.

The rules, over every trial of each arm:

- Downgrade: the step-down arm's recall is at least the current arm's, its
  clean-fixture false positives are no more than the current arm's, and every
  one of its trials produced output the grader could judge (`pass` or
  `graded_fail`).
- Upgrade: on some fixture with an expected finding, the step-up arm passes at
  least half its trials and the current arm passes none of its trials; and, as
  for a downgrade, the step-up arm's clean-fixture false positives are no more
  than the current arm's and every one of its trials produced gradeable output.
- An upgrade wins over a downgrade that also passes: the current tier misses a
  finding outright, and a cheaper tier cannot add it back.
- Anything else, and every blocked run, is `keep` with a stated reason.

An expected finding is a fixture whose expected entry is not clean: a trial that
passes on it caught what the fixture planted. Recall is passes over trials on
those fixtures. A run is blocked when it is incomplete, when its graded trials
cannot justify a tier change (rubric-judged evidence needs `RUBRIC_TRIALS` per
arm per fixture), or when the agent's results are excluded from evidence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .arm import BASELINE_LABEL
from .arm_totals import is_clean_fixture_false_positive
from .eligibility import tier_change_eligible
from .grader_config import AgentGrading, GraderKind
from .outcome import GRADED_OUTCOMES, Outcome
from .run_status import AbortReason
from .run_types import ArmRun
from .stress_arms import STEP_DOWN_LABEL, STEP_UP_LABEL
from .trial_count import RUBRIC_TRIALS

DECISION_KEEP = "keep"
DECISION_DOWNGRADE = "downgrade"
DECISION_UPGRADE = "upgrade"
# Agents whose results are excluded from evidence, with the reason the log states.
RECALL_GAP_EXCLUDED_AGENTS = {
    "correctness-review": (
        "correctness-review recall gap is known and unfixed; "
        "its results are excluded from evidence"
    ),
}


@dataclass(frozen=True)
class FixtureTally:
    """One arm's trials on one fixture and how many passed."""

    stem: str
    expected_clean: bool
    trials: int
    passes: int


@dataclass(frozen=True)
class ArmTally:
    """What the verdict needs from one arm.

    `ungraded` maps an outcome value to how many trials ended in it without a
    graded answer (parse failure, timeout, CLI error, tool violation, judge error).
    """

    label: str
    model: str
    effort: str
    fixtures: tuple[FixtureTally, ...]
    clean_false_positives: int
    ungraded: Mapping[str, int]

    @property
    def recall(self) -> tuple[int, int]:
        """Passes and trials on the fixtures that expect a finding."""
        finding_fixtures = [f for f in self.fixtures if not f.expected_clean]
        return (
            sum(f.passes for f in finding_fixtures),
            sum(f.trials for f in finding_fixtures),
        )

    def fixture(self, stem: str) -> FixtureTally | None:
        return next((f for f in self.fixtures if f.stem == stem), None)


@dataclass(frozen=True)
class Verdict:
    """The decision, why, and the arm whose tier it moves to (None for keep)."""

    decision: str
    reason: str
    arm_label: str | None
    model: str | None
    effort: str | None
    # None when a blocker stopped the comparison.
    downgrade_passes: bool | None
    downgrade_reason: str
    # The expected findings step-up adds; listed even when another check blocks the upgrade.
    upgrade_findings: tuple[str, ...]
    upgrade_reason: str
    tallies: tuple[ArmTally, ...] = ()


def decide(
    current: ArmTally,
    step_down: ArmTally | None,
    step_up: ArmTally | None,
) -> Verdict:
    """Apply the downgrade and upgrade rules to the three arms' tallies."""
    downgrade_failures = _downgrade_failures(current, step_down)
    downgrade_reason = (
        "; ".join(downgrade_failures)
        if downgrade_failures
        else "recall, clean-fixture false positives and parse all hold"
    )
    findings = _upgrade_findings(current, step_up)
    upgrade_failures = (
        _quality_failures(current, step_up, f"{STEP_UP_LABEL} has ")
        if findings and step_up is not None
        else []
    )
    upgrade_reason = _upgrade_reason(current, step_up, findings, upgrade_failures)
    tallies = tuple(t for t in (current, step_down, step_up) if t is not None)
    common = {
        "downgrade_passes": not downgrade_failures,
        "downgrade_reason": downgrade_reason,
        "upgrade_findings": findings,
        "upgrade_reason": upgrade_reason,
        "tallies": tallies,
    }
    if findings and not upgrade_failures and step_up is not None:
        return _moving_verdict(DECISION_UPGRADE, upgrade_reason, step_up, common)
    if not downgrade_failures and step_down is not None:
        return _moving_verdict(DECISION_DOWNGRADE, downgrade_reason, step_down, common)
    return Verdict(
        decision=DECISION_KEEP,
        reason=f"downgrade: {downgrade_reason}. upgrade: {upgrade_reason}",
        arm_label=None,
        model=None,
        effort=None,
        **common,
    )


def _moving_verdict(
    decision: str, reason: str, arm: ArmTally, common: dict
) -> Verdict:
    return Verdict(
        decision=decision,
        reason=reason,
        arm_label=arm.label,
        model=arm.model,
        effort=arm.effort,
        **common,
    )


def _downgrade_failures(current: ArmTally, lower: ArmTally | None) -> list[str]:
    if lower is None:
        return [_no_arm_reason(STEP_DOWN_LABEL, current, "lower")]
    failures = []
    lower_passes, lower_trials = lower.recall
    current_passes, current_trials = current.recall
    # Cross-multiplied, so unequal trial counts compare as rates without rounding.
    if lower_passes * current_trials < current_passes * lower_trials:
        failures.append(
            f"recall {lower_passes}/{lower_trials} below the current tier's "
            f"{current_passes}/{current_trials}"
        )
    return failures + _quality_failures(current, lower)


def _quality_failures(current: ArmTally, other: ArmTally, prefix: str = "") -> list[str]:
    """What blocks moving to `other` beyond recall: extra clean-fixture false positives, ungraded trials."""
    failures = []
    if other.clean_false_positives > current.clean_false_positives:
        failures.append(
            f"{prefix}{other.clean_false_positives} clean-fixture false positives, "
            f"above the current tier's {current.clean_false_positives}"
        )
    ungraded = {k: v for k, v in other.ungraded.items() if v}
    if ungraded:
        detail = ", ".join(f"{name} {count}" for name, count in ungraded.items())
        failures.append(
            f"{prefix}{sum(ungraded.values())} trial(s) with no gradeable output "
            f"({detail})"
        )
    return failures


def _upgrade_findings(current: ArmTally, higher: ArmTally | None) -> tuple[str, ...]:
    if higher is None:
        return ()
    caught = []
    for fixture in higher.fixtures:
        if fixture.expected_clean or fixture.trials == 0:
            continue
        mine = current.fixture(fixture.stem)
        if mine is None or mine.trials == 0 or mine.passes > 0:
            continue
        if 2 * fixture.passes >= fixture.trials:
            caught.append(fixture.stem)
    return tuple(caught)


def _no_arm_reason(label: str, current: ArmTally, rung: str) -> str:
    return (
        f"no {label} arm: {current.model}/{current.effort} has no {rung} rung "
        "on the model or effort ladder"
    )


def _upgrade_reason(
    current: ArmTally,
    higher: ArmTally | None,
    findings: tuple[str, ...],
    failures: list[str],
) -> str:
    if higher is None:
        return _no_arm_reason(STEP_UP_LABEL, current, "higher")
    if not findings:
        return (
            "step-up catches no expected finding in at least half its trials "
            "that the current tier misses in every trial"
        )
    caught = (
        f"step-up catches {', '.join(findings)} in at least half its trials; "
        "the current tier misses it in every trial"
    )
    return f"{caught}; but {'; '.join(failures)}" if failures else caught


def tally(arm_run: ArmRun) -> ArmTally:
    """Count one arm's passes per fixture, clean-fixture false positives and ungraded trials."""
    ungraded = Counter(
        result.outcome.value
        for result in arm_run.results
        if result.outcome not in GRADED_OUTCOMES
    )
    return ArmTally(
        label=arm_run.arm.label,
        model=arm_run.arm.model,
        effort=arm_run.arm.effort,
        fixtures=tuple(
            FixtureTally(
                stem=fixture.stem,
                expected_clean=fixture.expected_clean,
                trials=len(fixture.results),
                passes=sum(1 for r in fixture.results if r.outcome is Outcome.PASS),
            )
            for fixture in arm_run.fixture_trials
        ),
        clean_false_positives=sum(
            1
            for fixture in arm_run.fixture_trials
            for result in fixture.results
            if is_clean_fixture_false_positive(fixture, result)
        ),
        ungraded={o.value: ungraded[o.value] for o in Outcome if ungraded[o.value]},
    )


def stress_verdict(
    agent: str,
    arm_runs: Sequence[ArmRun],
    grading: AgentGrading,
    fixture_stems: Sequence[str],
    abort_reason: AbortReason | None,
) -> Verdict:
    """The verdict for a stress run, or `keep` with the blocker that stopped it."""
    tallies = {arm_run.arm.label: tally(arm_run) for arm_run in arm_runs}
    blocker = _blocker(agent, arm_runs, grading, fixture_stems, abort_reason)
    if blocker is None and BASELINE_LABEL not in tallies:
        blocker = "the run has no current-tier arm to compare against"
    if blocker is not None:
        return Verdict(
            decision=DECISION_KEEP,
            reason=blocker,
            arm_label=None,
            model=None,
            effort=None,
            downgrade_passes=None,
            downgrade_reason=blocker,
            upgrade_findings=(),
            upgrade_reason=blocker,
            tallies=tuple(tallies.values()),
        )
    return decide(
        tallies[BASELINE_LABEL],
        tallies.get(STEP_DOWN_LABEL),
        tallies.get(STEP_UP_LABEL),
    )


def _blocker(
    agent: str,
    arm_runs: Sequence[ArmRun],
    grading: AgentGrading,
    fixture_stems: Sequence[str],
    abort_reason: AbortReason | None,
) -> str | None:
    if agent in RECALL_GAP_EXCLUDED_AGENTS:
        return RECALL_GAP_EXCLUDED_AGENTS[agent]
    if abort_reason is not None:
        return f"run incomplete ({abort_reason.value}): only a complete run can move a tier"
    if not tier_change_eligible(arm_runs, grading, fixture_stems):
        if grading.kind is GraderKind.RUBRIC:
            return (
                f"rubric-judged evidence needs {RUBRIC_TRIALS} graded trials per arm "
                "per fixture to move a tier"
            )
        return "some arm has no graded trial on some fixture"
    return None


def verdict_dict(verdict: Verdict) -> dict:
    """The artifact's `verdict` object: what the decision log's gate checks a row against."""
    return {
        "decision": verdict.decision,
        "reason": verdict.reason,
        "arm": verdict.arm_label,
        "model": verdict.model,
        "effort": verdict.effort,
        "downgrade": {
            "passes": verdict.downgrade_passes,
            "reason": verdict.downgrade_reason,
        },
        "upgrade": {
            "findings": list(verdict.upgrade_findings),
            "reason": verdict.upgrade_reason,
        },
        "recall": {
            t.label: {"passes": t.recall[0], "trials": t.recall[1]}
            for t in verdict.tallies
        },
    }
