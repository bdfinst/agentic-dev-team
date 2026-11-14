"""Estimate what a run will cost before it starts.

The estimate is deliberately rough and can be several times off in either
direction: it models the text the agent is given and the answer it writes, not
the harness's own context overhead. All input tokens are priced at the model's
input rate, so cache reads (billed at a fraction of that rate) make it high,
while the fixed per-turn context makes it low. In the one real run the estimate
was 4.6 to 13.6 times the reported cost.

Pure functions: the pricing table is a parameter and the only file access is
measuring fixture sizes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import external, invocation
from .arm import Arm
from .cost import total_cost_usd
from .errors import UsageError
from .fixtures import ResolvedFixture
from .rubric_file import Judge
from .rubric_judge import JUDGE_SYSTEM_PROMPT, fixture_material

if TYPE_CHECKING:
    from .outcome import TrialResult

# A common rule of thumb for English prose and source code.
CHARS_PER_TOKEN = 4
# A trial with tools re-sends its growing context on every turn. The recorded
# read-only probe (tests/scripts/fixtures/model_effort_ab/pass-readonly.jsonl)
# took 3 model turns (two Read tool calls, then the answer), so input is
# counted 3 times.
TOOL_TURN_MULTIPLIER = 3
# Output tokens one trial is assumed to write, thinking included. The probe wrote
# 230 for a trivial one-line answer; a findings JSON from a review agent runs
# several times that, and thinking tokens bill as output.
OUTPUT_TOKENS_PER_TRIAL = 2000
TOKENS_PER_RATE_UNIT = 1_000_000
# Output tokens one rubric judgement is assumed to write: a verdict and a reason per criterion.
JUDGE_OUTPUT_TOKENS_PER_TRIAL = 800
PRICING_FILE_HINT = "plugins/dev-team/knowledge/model-pricing.json"


@dataclass(frozen=True)
class RunEstimate:
    """Estimated dollars per arm label, in arm order, and the trials each arm plans in total.

    `total_trials_per_arm` is fixtures times `--trials`: every trial one arm runs.
    """

    by_arm: tuple[tuple[str, float], ...]
    total_trials_per_arm: int
    # The rubric judge's estimated dollars over every trial of every arm; 0.0 without a judge.
    judge_usd: float = 0.0
    # How many arms share the judge estimate, to price one judgement.
    arm_count: int = 2

    @property
    def estimated_total_usd(self) -> float:
        return total_cost_usd([*(cost_usd for _, cost_usd in self.by_arm), self.judge_usd])

    def cost_usd_for_arm(self, label: str) -> float:
        return dict(self.by_arm)[label]

    def per_trial_usd(self, label: str) -> float:
        """The arm's estimate averaged over its planned trials."""
        return self.cost_usd_for_arm(label) / self.total_trials_per_arm

    def charged_usd(self, label: str, result: TrialResult) -> float:
        """What a trial counts for toward the spend limit and the artifact's unreported-trials estimate.

        Its reported cost, or the arm's per-trial estimate when the stream reported none.
        """
        return (
            result.reported_cost_usd
            if result.cost_reported
            else self.per_trial_usd(label)
        )

    def per_judgement_usd(self) -> float:
        """The judge estimate averaged over every planned judgement."""
        return self.judge_usd / (self.total_trials_per_arm * self.arm_count)

    def charged_judge_usd(self, result: TrialResult) -> float:
        """What a trial's judgement counts for, by `charged_usd`'s rule.

        Its reported cost, or the per-judgement estimate when a judge ran and
        reported none; 0.0 when no judge ran.
        """
        if result.judge_cost_usd is not None:
            return result.judge_cost_usd
        return self.per_judgement_usd() if result.judged else 0.0

    def total_charged_usd(self, label: str, result: TrialResult) -> float:
        """The trial and its judgement together: what the spend limit counts."""
        return self.charged_usd(label, result) + self.charged_judge_usd(result)


def fixture_size_bytes(path: Path) -> int:
    """Return a file's size, or the summed size of every file under a directory."""
    if path.is_dir():
        return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
    return path.stat().st_size


def estimate_run(
    arms: Sequence[Arm],
    system_prompt: str,
    fixtures: Sequence[ResolvedFixture],
    trials_per_fixture: int,
    pricing_table: dict,
    judge: Judge | None = None,
    judge_sees_changes: bool = False,
) -> RunEstimate:
    """Estimate each arm's cost: (input + output allowance) priced, times fixtures times trials.

    With a rubric `judge`, also estimate one judgement per trial of every arm;
    `judge_sees_changes` (a sandboxed agent) adds an answer-sized allowance for
    the diff of what the trial changed.

    Raises:
        UsageError: an arm's or the judge's model has no rate in `pricing_table`.
    """
    rates = _rates_by_arm(arms, pricing_table)
    input_tokens = sum(_input_tokens(system_prompt, fixture) for fixture in fixtures)
    return RunEstimate(
        by_arm=tuple(
            (
                arm.label,
                _arm_cost_usd(
                    rates[arm.label], input_tokens, len(fixtures), trials_per_fixture
                ),
            )
            for arm in arms
        ),
        total_trials_per_arm=len(fixtures) * trials_per_fixture,
        arm_count=len(arms),
        judge_usd=(
            _judge_cost_usd(judge, fixtures, pricing_table, judge_sees_changes)
            * trials_per_fixture
            * len(arms)
            if judge is not None
            else 0.0
        ),
    )


def _judge_cost_usd(
    judge: Judge,
    fixtures: Sequence[ResolvedFixture],
    pricing_table: dict,
    sees_changes: bool = False,
) -> float:
    """One judgement on each fixture: rubric, points, task, material and an answer-sized
    allowance in (twice, when the judge also sees the trial's changes); verdicts out."""
    rate = external.pricing().rate(pricing_table, judge.model)
    if rate is None:
        raise UsageError(
            f"no price for the rubric judge model {judge.model!r}: add it to "
            f"{PRICING_FILE_HINT}, because the cost estimate and spend limit need a rate"
        )
    answer_chars = OUTPUT_TOKENS_PER_TRIAL * CHARS_PER_TOKEN * (2 if sees_changes else 1)
    total = 0.0
    for fixture in fixtures:
        input_chars = (
            len(JUDGE_SYSTEM_PROMPT)
            + len(judge.rubric_text)
            + sum(len(point_id) + len(text) for point_id, text in fixture.rubric_points)
            + len(invocation.build_user_prompt(fixture.path.name, fixture.task))
            + len(fixture_material(fixture.path))
            + answer_chars
        )
        total += (
            input_chars / CHARS_PER_TOKEN * rate["input"]
            + JUDGE_OUTPUT_TOKENS_PER_TRIAL * rate["output"]
        ) / TOKENS_PER_RATE_UNIT
    return total


def _rates_by_arm(arms: Sequence[Arm], pricing_table: dict) -> dict[str, dict]:
    rates = {
        arm.label: external.pricing().rate(pricing_table, arm.model) for arm in arms
    }
    unpriced = [arm for arm in arms if rates[arm.label] is None]
    if unpriced:
        named = ", ".join(f"{arm.model!r} ({arm.label} arm)" for arm in unpriced)
        raise UsageError(
            f"no price for model {named}: add it to {PRICING_FILE_HINT} "
            "or choose a priced model, because the cost estimate and spend limit need a rate"
        )
    return rates


def _input_tokens(system_prompt: str, fixture: ResolvedFixture) -> float:
    """Input tokens one trial on `fixture` is assumed to send, all turns included."""
    chars = (
        len(system_prompt)
        + fixture_size_bytes(fixture.path)
        + len(invocation.build_user_prompt(fixture.path.name, fixture.task))
    )
    return chars / CHARS_PER_TOKEN * TOOL_TURN_MULTIPLIER


def _arm_cost_usd(
    rate: dict, input_tokens: float, fixture_count: int, trials_per_fixture: int
) -> float:
    """`input_tokens` is summed over fixtures; the output allowance is per fixture."""
    output_tokens = OUTPUT_TOKENS_PER_TRIAL * fixture_count
    cost_per_round_usd = (
        input_tokens * rate["input"] + output_tokens * rate["output"]
    ) / TOKENS_PER_RATE_UNIT
    return cost_per_round_usd * trials_per_fixture
