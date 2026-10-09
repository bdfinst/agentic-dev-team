"""The run session (model_effort.session)."""

from __future__ import annotations

import io
import json

import pytest
from _model_effort_support import ARM_COUNT, _arm_run, _run_estimate, _trial_result
from model_effort import run_types, session
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL
from model_effort.outcome import Outcome
from model_effort.run_status import AbortReason


def _run_with_one_trial_each(abort_reason: AbortReason | None) -> run_types.RunResult:
    passed = [_trial_result(Outcome.PASS)]
    return run_types.RunResult(
        arm_runs=[_arm_run(BASELINE_LABEL, passed), _arm_run(CANDIDATE_LABEL, passed)],
        abort_reason=abort_reason,
        started_trials=ARM_COUNT,
        stopping_trial=None,
    )


class UnwritableStream:
    """A stderr whose reader has gone away."""

    def write(self, _text: str) -> int:
        raise BrokenPipeError("reader closed")

    def flush(self) -> None:
        pass


class TestFinishRun:
    def test_run_cut_short_before_any_trial_started_writes_no_artifact_and_says_so(
        self, scout_plan
    ):
        stderr = io.StringIO()
        console = session.Console(io.StringIO(), lambda: False, io.StringIO(), stderr)
        run = run_types.RunResult(
            arm_runs=[],
            abort_reason=AbortReason.INTERRUPT,
            started_trials=0,
            stopping_trial=None,
        )

        code = session.finish_run(scout_plan, run, _run_estimate(), console)

        assert code == 1
        assert scout_plan.artifact_path.read_text(encoding="utf-8") == ""
        assert "interrupted before any trial started" in stderr.getvalue()

    def test_artifact_is_saved_before_the_stop_notice_is_printed(self, scout_plan):
        console = session.Console(
            io.StringIO(), lambda: False, io.StringIO(), UnwritableStream()
        )
        run = _run_with_one_trial_each(AbortReason.MAX_COST)

        with pytest.raises(BrokenPipeError):
            session.finish_run(scout_plan, run, _run_estimate(), console)

        saved = json.loads(scout_plan.artifact_path.read_text(encoding="utf-8"))
        assert (saved["status"], saved["abort_reason"]) == ("incomplete", "max-cost")
