"""One side of the A/B comparison: the model, effort and tool profile a trial runs with."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .tools import ToolProfile

BASELINE_LABEL = "baseline"
CANDIDATE_LABEL = "candidate"


@dataclass(frozen=True)
class Arm:
    """The single definition of an arm. Trial configuration and the artifact derive from it."""

    label: str
    model: str
    effort: str
    profile: ToolProfile


def arm_by_label(arms: Iterable[Arm], label: str) -> Arm:
    """Return the arm with `label`; raises LookupError if there is none."""
    for arm in arms:
        if arm.label == label:
            return arm
    raise LookupError(f"no arm labelled {label!r}")
