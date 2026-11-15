"""The artifact's reservation and final write, and what a failed write leaves behind."""

from __future__ import annotations

import json

import pytest
from ab_constants import CLEAN_FORM_ARGS, RUN_ID
from ab_results import store_with_failing_replace
from ab_world import RaisingStdin, cli, gated_cli, passing_stub


class TestArtifactReservationAndWrite:
    def test_run_that_fails_before_any_trial_starts_leaves_no_placeholder(self, world):
        stdin = RaisingStdin(RuntimeError("stdin closed"))

        with pytest.raises(RuntimeError):
            gated_cli(world, passing_stub(world), stdin)

        assert world.artifacts == []

    def test_failed_final_write_prints_the_artifact_to_stdout_exits_1_and_leaves_no_files(
        self, world, capsys, monkeypatch
    ):
        stub = passing_stub(world)
        store_with_failing_replace(monkeypatch)

        code = cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        captured = capsys.readouterr()
        printed = json.loads(captured.out)
        assert code == 1
        assert printed["run_id"] == RUN_ID and printed["status"] == "complete"
        assert "stdout" in captured.err
        assert world.artifacts == []

    def test_failed_final_write_keeps_a_placeholder_that_gained_content(
        self, world, monkeypatch
    ):
        stub = passing_stub(world, touch=str(world.artifact_path))
        store_with_failing_replace(monkeypatch)

        code = cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        assert code == 1
        assert world.artifact_path.read_text(encoding="utf-8") == (
            "created during the run"
        )
        assert world.artifacts == [world.artifact_path]
