"""One side of the A/B comparison: the model, effort and tool profile a trial runs with."""

from __future__ import annotations

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
