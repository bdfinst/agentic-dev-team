"""Run id construction (model_effort.run_id)."""

from __future__ import annotations

from _model_effort_support import NOW, RUN_ID, FixedRng
from model_effort import run_id


class TestRunId:
    def test_run_id_joins_utc_time_agent_candidate_model_effort_and_four_hex(self):
        made = run_id.make_run_id(NOW, "scout", "haiku", "high", FixedRng())

        assert made == RUN_ID
