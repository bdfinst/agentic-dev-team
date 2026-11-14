"""How many trials each arm runs per fixture, and why that number was chosen."""

from __future__ import annotations

from dataclasses import dataclass

from .grader_config import GraderKind

RUBRIC_GRADER = GraderKind.RUBRIC.value

# Exact agent names: `security-reviewer` is not in the set.
HIGH_STAKES_AGENTS = frozenset(
    {"security-review", "correctness-review", "architect", "security-engineer"}
)
DEFAULT_TRIALS = 5
HIGH_STAKES_TRIALS = 10
# Rubric-judged evidence moves a tier only with this many trials per arm per fixture.
RUBRIC_TRIALS = 10
TRIALS_DEFAULT_REASON = "default"
TRIALS_HIGH_STAKES_REASON = "high-stakes default"
TRIALS_RUBRIC_REASON = "rubric-judged default"
TRIALS_FLAG_REASON = "--trials"


@dataclass(frozen=True)
class TrialCount:
    """Trials per arm per fixture, and why that number was chosen."""

    count: int
    reason: str


def resolve_trials(
    flag_value: int | None, agent: str, *, rubric_judged: bool = False
) -> TrialCount:
    """Return `--trials` if given, else the high-stakes, rubric-judged or general default."""
    if flag_value is not None:
        return TrialCount(flag_value, TRIALS_FLAG_REASON)
    if agent in HIGH_STAKES_AGENTS:
        return TrialCount(HIGH_STAKES_TRIALS, TRIALS_HIGH_STAKES_REASON)
    if rubric_judged:
        return TrialCount(RUBRIC_TRIALS, TRIALS_RUBRIC_REASON)
    return TrialCount(DEFAULT_TRIALS, TRIALS_DEFAULT_REASON)


def can_justify_tier_change(grader: str, trials_per_arm: int) -> bool:
    """True when a run graded by `grader` with this many trials per arm per fixture may move a tier.

    Rubric-judged evidence needs `RUBRIC_TRIALS`; deterministic graders have no floor here.
    """
    return grader != RUBRIC_GRADER or trials_per_arm >= RUBRIC_TRIALS
