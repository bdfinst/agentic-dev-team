"""Estimate what a run will cost before it starts.

The estimate is deliberately rough and errs low: it models the text the agent is
given and the answer it writes, not the harness's own context overhead. All input
tokens are priced at the model's input rate, so cache reads (billed at a fraction
of that rate) make it high, while the fixed per-turn context makes it low.

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
PRICING_FILE_HINT = "plugins/dev-team/knowledge/model-pricing.json"


@dataclass(frozen=True)
class RunEstimate:
    """Estimated dollars per arm label, in arm order, and the trials each arm plans in total.

    `total_trials_per_arm` is fixtures times `--trials`: every trial one arm runs.
    """

    by_arm: tuple[tuple[str, float], ...]
    total_trials_per_arm: int

    @property
    def estimated_total_usd(self) -> float:
        return total_cost_usd(cost_usd for _, cost_usd in self.by_arm)

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
) -> RunEstimate:
    """Estimate each arm's cost: (input + output allowance) priced, times fixtures times trials.

    Raises:
        UsageError: an arm's model has no rate in `pricing_table`.
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
    )


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
        + len(invocation.build_user_prompt(fixture.path.name))
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
