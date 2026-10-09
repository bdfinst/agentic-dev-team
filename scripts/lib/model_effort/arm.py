"""One side of the A/B comparison: the model and effort a trial runs with."""

from __future__ import annotations

from dataclasses import dataclass

BASELINE_LABEL = "baseline"
CANDIDATE_LABEL = "candidate"


@dataclass(frozen=True)
class Arm:
    """The single definition of an arm. Trial configuration and the artifact derive from it.

    Both arms share one tool profile, which belongs to the run plan, so that only
    the model and effort differ.
    """

    label: str
    model: str
    effort: str
