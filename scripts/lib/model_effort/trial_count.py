"""How many trials each arm runs per fixture, and why that number was chosen."""

from __future__ import annotations

from dataclasses import dataclass

# Exact agent names: `security-reviewer` is not in the set.
HIGH_STAKES_AGENTS = frozenset(
    {"security-review", "correctness-review", "architect", "security-engineer"}
)
DEFAULT_TRIALS = 5
HIGH_STAKES_TRIALS = 10
TRIALS_DEFAULT_REASON = "default"
TRIALS_HIGH_STAKES_REASON = "high-stakes default"
TRIALS_FLAG_REASON = "--trials"


@dataclass(frozen=True)
class TrialCount:
    """Trials per arm per fixture, and why that number was chosen."""

    count: int
    reason: str


def resolve_trials(flag_value: int | None, agent: str) -> TrialCount:
    """Return `--trials` if given, else the high-stakes or the general default."""
    if flag_value is not None:
        return TrialCount(flag_value, TRIALS_FLAG_REASON)
    if agent in HIGH_STAKES_AGENTS:
        return TrialCount(HIGH_STAKES_TRIALS, TRIALS_HIGH_STAKES_REASON)
    return TrialCount(DEFAULT_TRIALS, TRIALS_DEFAULT_REASON)
