"""Why a run ended early, and whether it counts as complete."""

from __future__ import annotations

from enum import StrEnum


class AbortReason(StrEnum):
    """Why a run ended before every planned trial ran. Values are the artifact's JSON strings."""

    MAX_COST = "max-cost"
    INFRA_FAILURE = "infra-failure"
    INTERRUPT = "interrupt"
    HARNESS_ERROR = "harness-error"


class RunStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"

    @classmethod
    def of(cls, abort_reason: AbortReason | None) -> RunStatus:
        """A run is incomplete exactly when something ended it early."""
        return cls.COMPLETE if abort_reason is None else cls.INCOMPLETE
