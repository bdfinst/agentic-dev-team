"""Run a planned set of trials: both arms alternate trial by trial on each fixture.

Alternation means a broken candidate fails on its first trial instead of after
the whole baseline arm has been paid for.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from . import interrupts, invocation, paths, rubric_judge, stop_rules, transcript
from .arm import Arm
from .cost import total_cost_usd
from .estimate import RunEstimate
from .fixtures import ResolvedFixture
from .grader_config import GraderKind
from .grading import grade_trial
from .outcome import MAX_MESSAGE_CHARS, Outcome, TrialResult, resolve_outcome
from .plan import RunPlan
from .process_record import TrialProcessRecord
from .run_status import AbortReason
from .run_types import (
    ArmRun,
    FixtureTrials,
    RunResult,
    TrialProgress,
    TrialSettings,
)
from .stop_rules import SpendLimit

# Runs one trial of a config against a fixture; `runner.run_trial` in production.
TrialRunner = Callable[[Path, invocation.TrialConfig, float], TrialProcessRecord]
# Graders that need the agent's JSON answer; the others grade the transcript's
# dispatches, the sandbox's test results or the answer's prose, so an answer with
# no JSON is still graded (a dispatch-set entry that expects a verdict fails it).
JSON_GRADED_KINDS = frozenset({GraderKind.EXPECTED_FINDINGS})


@dataclass(frozen=True)
class _TrialSlot:
    arm: Arm
    fixture: ResolvedFixture
    fixture_number: int
    trial_number: int


class _Ledger:
    """Completed trials so far, in the shapes the stop rules and the artifact need."""

    def __init__(self, plan: RunPlan, run_estimate: RunEstimate) -> None:
        self._plan = plan
        self._run_estimate = run_estimate
        self._results_by_arm_and_fixture: dict[tuple[str, str], list[TrialResult]] = {}
        self._outcomes_by_arm: dict[str, list[Outcome]] = {
            arm.label: [] for arm in plan.arms
        }
        self._charged_usd: list[float] = []

    def record(self, slot: _TrialSlot, result: TrialResult) -> None:
        key = (slot.arm.label, slot.fixture.stem)
        self._results_by_arm_and_fixture.setdefault(key, []).append(result)
        self._outcomes_by_arm[slot.arm.label].append(result.outcome)
        self._charged_usd.append(
            self._run_estimate.total_charged_usd(slot.arm.label, result)
        )

    @property
    def outcomes_by_arm(self) -> Mapping[str, list[Outcome]]:
        return self._outcomes_by_arm

    @property
    def cumulative_charged_usd(self) -> float:
        return total_cost_usd(self._charged_usd)

    def arm_runs(self, trials_per_fixture: int) -> list[ArmRun]:
        return [
            ArmRun(
                arm=arm,
                trials_per_fixture=trials_per_fixture,
                fixture_trials=[
                    FixtureTrials(
                        stem=fixture.stem,
                        kind=fixture.kind,
                        expected_clean=fixture.expected_clean,
                        expected_skip=fixture.expected_skip,
                        results=self._results_by_arm_and_fixture[
                            (arm.label, fixture.stem)
                        ],
                    )
                    for fixture in self._plan.fixtures
                    if (arm.label, fixture.stem) in self._results_by_arm_and_fixture
                ],
            )
            for arm in self._plan.arms
        ]


def run_trials(
    plan: RunPlan,
    settings: TrialSettings,
    run_estimate: RunEstimate,
    *,
    run_trial: TrialRunner,
    spend_limit: SpendLimit | None = None,
    on_trial: Callable[[TrialProgress], None] | None = None,
    run_judge_process: rubric_judge.ProcessRunner | None = None,
) -> RunResult:
    """Run trials in order until the plan is done, a stop rule fires or the run is cut short.

    `run_estimate` prices a trial or a rubric judgement that reports no cost, so the
    spend limit still sees it; a judge's reported cost is charged, failed judgements included. `run_judge_process` runs the
    judge's CLI process (`runner.run_cli_process` in production); a rubric-graded
    plan needs it.
    `on_trial` is called after each completed trial, before the stop rules run.
    A stop on the last planned trial skips nothing, so the stop rules ignore it. An
    operator interrupt or an unexpected error keeps the completed trials.

    The caller holds the interrupt signals (see `interrupts`), so a signal never
    drops a trial that finished. One that arrived while a trial was being resolved,
    graded or recorded is found before the next trial starts and ends the run.
    """
    executor = _TrialExecutor(plan, settings, run_trial, run_judge_process)
    ledger = _Ledger(plan, run_estimate)
    slots = list(executor.slots())
    started_trials = 0
    abort_reason: AbortReason | None = None
    stopping_trial: TrialProgress | None = None
    harness_error: str | None = None
    try:
        for index, slot in enumerate(slots):
            interrupts.raise_if_pending()
            started_trials += 1
            result = executor.run(slot)
            ledger.record(slot, result)
            progress = executor.progress(slot, result)
            if on_trial is not None:
                on_trial(progress)
            stop_reason = stop_rules.check_stop(
                ledger.outcomes_by_arm,
                ledger.cumulative_charged_usd,
                spend_limit,
                trials_remaining=len(slots) - index - 1,
            )
            if stop_reason is not None:
                abort_reason = stop_reason
                stopping_trial = progress
                break
    except KeyboardInterrupt:
        abort_reason = AbortReason.INTERRUPT
    except Exception as error:  # noqa: BLE001 - keep the paid trials whatever failed
        abort_reason = AbortReason.HARNESS_ERROR
        harness_error = f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]
    return RunResult(
        arm_runs=ledger.arm_runs(settings.trials.count),
        abort_reason=abort_reason,
        started_trials=started_trials,
        stopping_trial=stopping_trial,
        harness_error=harness_error,
    )


@dataclass(frozen=True)
class _TrialExecutor:
    """Runs one planned trial at a time; carries the plan, settings and runner once."""

    plan: RunPlan
    settings: TrialSettings
    run_trial: TrialRunner
    run_judge_process: rubric_judge.ProcessRunner | None = None

    def slots(self) -> Iterator[_TrialSlot]:
        """Every planned trial in run order: arms alternate, round by round, fixture by fixture."""
        for fixture_number, fixture in enumerate(self.plan.fixtures, start=1):
            for trial_number in range(1, self.settings.trials.count + 1):
                for arm in self.plan.arms:
                    yield _TrialSlot(arm, fixture, fixture_number, trial_number)

    def run(self, slot: _TrialSlot) -> TrialResult:
        """Run the slot's trial against its fixture, parse the stream and resolve the outcome."""
        config = invocation.TrialConfig(
            arm=slot.arm,
            system_prompt=self.plan.system_prompt,
            profile=self.plan.profile,
            snapshot_paths=self.plan.snapshot.paths,
            claude_bin=self.settings.claude_bin,
            task=slot.fixture.task,
            stub_agents=self.plan.stub_agents,
            sandbox=self.plan.grading.sandbox,
            test_commands=slot.fixture.test_commands,
            protected_paths=slot.fixture.protected_paths,
            deny_read=self._answer_dirs(),
            deny_write=(self.plan.snapshot.root, *self._answer_dirs()),
            check_jail=self.plan.check_jail,
        )
        record = self.run_trial(
            slot.fixture.path, config, self.settings.trial_timeout_seconds
        )
        parsed = transcript.parse_stream(record.stdout)
        grader = _KindGrader(self, slot.fixture, record, parsed)
        result = resolve_outcome(
            record,
            parsed,
            self.plan.profile.enabled_tools,
            grader,
            snapshot_dir=self.plan.snapshot.root,
            requires_agent_json=self.plan.grading.kind in JSON_GRADED_KINDS,
            fail_on_permission_denials=self.plan.grading.sandbox,
        )
        if not grader.judged:
            return result
        return dataclasses.replace(
            result, judge_cost_usd=grader.judge_cost_usd, judged=True
        )

    def _answer_dirs(self) -> tuple[Path, ...]:
        """Where the answer key lives: the run's frozen copy, the repo's `evals/expected`,
        and the plan's other repo copies (git directory, every checkout's expected dir)."""
        return tuple(
            dict.fromkeys(
                (
                    self.plan.snapshot.paths.expected_dir,
                    paths.EXPECTED_DIR,
                    *self.plan.answer_key_paths,
                )
            )
        )

    def progress(self, slot: _TrialSlot, result: TrialResult) -> TrialProgress:
        return TrialProgress(
            arm_label=slot.arm.label,
            fixture_number=slot.fixture_number,
            fixture_count=len(self.plan.fixtures),
            fixture_stem=slot.fixture.stem,
            trial_number=slot.trial_number,
            trials_per_fixture=self.settings.trials.count,
            result=result,
        )


class _KindGrader:
    """Grades one trial the way the plan's grader kind says; called with the agent's JSON.

    Every kind ends in `scripts/eval_grade.py`: the expected-findings kind grades
    the JSON itself, the others grade what they record in its place (the
    dispatched agents, the sandbox's test results, the rubric judge's verdicts).
    Records what the rubric judge reported it cost, for the trial result.
    """

    def __init__(
        self,
        executor: _TrialExecutor,
        fixture: ResolvedFixture,
        record: TrialProcessRecord,
        parsed: transcript.ParsedTranscript,
    ) -> None:
        self._executor = executor
        self._fixture = fixture
        self._record = record
        self._parsed = parsed
        self.judge_cost_usd: float | None = None
        self.judged = False

    def __call__(self, agent_json: dict) -> tuple[bool, list[str]]:
        plan = self._executor.plan
        kind = plan.grading.kind
        if kind is GraderKind.DISPATCH_SET:
            actual = {
                "dispatched": list(self._parsed.dispatched_agents),
                "output": transcript.extract_agent_json(self._parsed.result_text),
            }
        elif kind is GraderKind.TESTS_PASS:
            actual = {"results": list(self._record.check_results)}
        elif kind is GraderKind.RUBRIC:
            judgement = self._judged()
            if judgement.failure is not None:
                return False, [f"rubric: {judgement.failure}"]
            actual = rubric_judge.judgement_actual(plan.grading.judge, judgement)
        else:
            actual = agent_json
        return grade_trial(
            plan.agent,
            self._fixture.stem,
            actual,
            plan.snapshot.paths.expected_dir,
        )

    def _judged(self) -> rubric_judge.Judgement:
        """Run the judge on this trial's answer, recording what it reported it cost."""
        plan = self._executor.plan
        judge = plan.grading.judge
        run_process = self._executor.run_judge_process
        if judge is None or run_process is None:
            raise RuntimeError("a rubric-graded run needs a judge and a process runner")
        self.judged = True
        try:
            judgement = rubric_judge.run_judge(
                judge,
                [
                    {"id": point_id, "requirement": requirement}
                    for point_id, requirement in self._fixture.rubric_points
                ],
                invocation.build_user_prompt(
                    self._fixture.path.name, self._fixture.task
                ),
                self._parsed.result_text or "",
                material=rubric_judge.fixture_material(self._fixture.path),
                changes=self._record.work_diff,
                claude_bin=self._executor.settings.claude_bin,
                timeout_seconds=self._executor.settings.trial_timeout_seconds,
                run_process=run_process,
            )
        except rubric_judge.JudgeError as error:
            self.judge_cost_usd = error.cost_usd
            raise
        self.judge_cost_usd = judgement.cost_usd
        return judgement
