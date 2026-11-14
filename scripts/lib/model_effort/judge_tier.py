"""The judge-tier ladder: a rubric judge must sit one model tier above the arms it judges."""

from __future__ import annotations

from .errors import UsageError
from .rubric_file import Judge

# Weakest first: the judge for an agent is the next entry, capped at the last.
MODEL_TIERS = ("haiku", "sonnet", "opus")


def model_tier(model: str) -> int | None:
    """Index in `MODEL_TIERS` for an alias or a full model ID; None when unknown."""
    lowered = model.lower()
    for index, tier in enumerate(MODEL_TIERS):
        if lowered == tier or f"-{tier}-" in f"-{lowered}-":
            return index
    return None


def required_judge_tier(arm_models: list[str]) -> int | None:
    """The lowest judge tier allowed: one above the strongest arm, capped at the top tier.

    None when an arm's model has no known tier.
    """
    tiers = [model_tier(model) for model in arm_models]
    if any(tier is None for tier in tiers):
        return None
    return min(max(tiers) + 1, len(MODEL_TIERS) - 1)


def check_judge_tier(judge: Judge, arm_models: list[str]) -> None:
    """Refuse a judge weaker than one tier above every arm under test.

    Raises:
        UsageError: an arm's or the judge's tier is unknown, or the judge is too weak.
    """
    required = required_judge_tier(arm_models)
    judge_tier = model_tier(judge.model)
    if required is None or judge_tier is None:
        raise UsageError(
            f"cannot place the judge {judge.model!r} or an arm "
            f"({', '.join(arm_models)}) on the {'/'.join(MODEL_TIERS)} ladder, so the "
            "rubric judge cannot be checked to sit one tier above the agent"
        )
    if judge_tier < required:
        raise UsageError(
            f"the rubric judge {judge.model!r} must be at least {MODEL_TIERS[required]} "
            f"to sit one tier above the arms ({', '.join(arm_models)}): pin a stronger "
            "judge in evals/model-effort/graders.json or choose a weaker candidate"
        )
